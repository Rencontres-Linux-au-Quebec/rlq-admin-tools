# Changelog

Version numbers follow `MAJOR.MINOR.YYYYMMDD.HHMMSS` (local time of the change).
Each program has its own section; the most recent version comes first.
Earlier history was archived outside this repository when this file was created.

## Repository conventions (CLAUDE.md)

### 0.1.20261101.173400 - Rules for bans behind CDNs and automatic bans

- Title: CLAUDE.md now forbids bans of CDN addresses without an attack signature and requires the audit score and notifications before automatic bans.
- Reason: on 2026-11-01, fail2ban banned an address of Cloudflare (CLOUDFLARENET 104.16.0.0/12) through the nginx-badrequests jail. The 14 counted hits were ordinary 404 and 30x responses on old event pages, and a real visitor behind the same node was affected. No notification was received because SMTP was not configured.
- Changes: CLAUDE.md, new section "Bans and CDNs" (four rules). No program code changed, so no program version was bumped.
- Bugs fixed: none in code. The rules describe the missing safeguards: CDN names are only filtered in app-log-live.py (CDN_NAME_RE) for the 404 sweep and web-monitor.py, not for the fail2ban jails; nginx sees the CDN node address instead of the visitor address (the CF-Connecting-IP header is not yet used).
- Safeguards and edge cases: rules only, nothing enforced by code yet. Follow-up work (real_ip configuration, filter regex, threshold) is not part of this change.
- Checks: text review of CLAUDE.md; no tests affected.
- Action required: none. Review the wording of the rules before merging.

## admin-menu.sh

### 1.1.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: none.
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

### 1.0.20261028.225816 - First version: one menu for all the programs that have --menu

- Title: admin-menu.sh lists the repository programs that offer --menu and starts the menu of the one chosen.
- Reason: Each program has its own menu (--menu), and the administrator had to remember each program name and its options. One entry point is needed, and dialog (the window menu) must be installed when it is missing.
- Name: admin-menu.sh rather than odoo-menu.sh. The tools also serve applications other than Odoo behind nginx, and the program names of the repository do not contain the name of an application.
- Details:
  - New file admin-menu.sh (bash, version from the readonly SCRIPT_VERSION variable, shown by --version).
  - Programs offered: every executable file of the folder whose text contains --menu (16 programs at this version, found at each run, so a new program appears without a change here). The PROGRAMS key restricts the list.
  - Menu: dialog when it is installed, otherwise a text menu. Each entry starts the program with --menu (and with --verbose when the verbose mode is on); the program then shows its own menu. A "Press Enter to return to the menu" pause follows each run.
  - Installation of dialog: offered at the start of the menu when it is missing (question, then apt-get update and apt-get install dialog, as root or with sudo). --install-dialog does the same without asking.
  - Options: --changelog, -c/--config FILE, -h/--help, --install-dialog, --list, --report-err, -v/--verbose, --version. Options are shown in colour in the help, sorted alphabetically.
  - Configuration: /etc/default/admin-menu.conf, then ~/.admin-menu.conf (last one wins; command line first). Keys: LANGUAGE (en, fr, auto), PROGRAMS (list of programs, empty for all), VERBOSE (yes or no). The file(s) really read are shown at each run.
  - Language: French or English according to LANGUAGE, otherwise LC_ALL, LC_MESSAGES, LANG.
  - Ctrl+C: asks for confirmation (apps/_i18n.sh, ctrl_c_child for the program started).
  - Files touched: admin-menu.sh (new), CHANGELOG.md (this section), doc/en/admin-menu.conf.example and doc/fr/admin-menu.conf.example (new configuration templates).
- Bugs fixed: none (first version).
- Safeguards and edge cases:
  - Without a terminal, the menu refuses with a message (exit 1); without option, the list of programs and the help are shown instead.
  - No program with --menu in the folder: the menu says so and exits.
  - A program that fails returns its code, which is shown; the menu stays open.
  - If apt-get update fails, the installation is still tried, with a warning.
  - Without root and without sudo, the installation is refused with a message; nothing is changed.
  - --changelog shows only this section; colours off when the output is redirected; a closed pipe ends quietly.
- Checks performed:
  - bash -n and ShellCheck 0.11.0 with -x: no warning.
  - --version, --help, --list, --changelog, unknown option, and the text menu inside a pseudo-terminal (choice of quit, colours and labels checked).
  - --install-dialog on a machine without access to the Ubuntu package archive: the program stops with a clear message, as designed.
  - Not verified here: the dialog window itself (dialog could not be installed in the test environment).
- Action required: run admin-menu.sh once on a terminal. If dialog is missing, answer o to install it; then check the window menu. No other action.

## odoo-sql-maint

### 1.4.20261028.202537 - Menu no longer captures dialog output (fix for "cannot open tty-output")

- Title: The menu asks dialog for its answer in a file instead of capturing its output.
- Reason: With a working terminal, running the menu still failed with "cannot open tty-output". Version 1.3 only added a clearer message for the case where no terminal exists; it did not fix this error, which happens in the menu itself.
- Changes:
  - New function dialog_run: runs dialog with --output-fd 3, writing the answer to a temporary file, and returns dialog's exit code.
  - run_menu uses dialog_run for the query list and the action list (previously "$(dialog --stdout ...)").
  - Confirmation boxes and message boxes were already called without capturing their output; they are unchanged.
  - Files: odoo-sql-maint.
- Bugs fixed:
  - Symptom: "cannot open tty-output" when starting the menu from a terminal where dialog itself works.
  - Diagnosis: with --stdout inside $(...), dialog's standard output is a pipe, so dialog looks for a terminal by name (from stderr, stdout or stdin, or /dev/tty) and opens it for writing. If that name cannot be opened, dialog stops with this message. This is dialog's code path in util.c.
  - Fix: dialog keeps the terminal as its screen; the answer goes to a file. The name lookup is not used.
- Safeguards and edge cases:
  - The temporary answer file is removed after each call, also when the user cancels (empty answer, non-zero code).
  - The no-terminal check added in 1.3 (check_tty) still runs first.
  - The CLI mode (--run) does not use dialog and is unchanged.
- Checks:
  - bash -n OK; shellcheck 0.11.0 no warning.
  - dialog 1.3 built from its source and tested in a pseudo-terminal (script): menu opens, choosing a query, running it and quitting work; the audit log records the run.
  - dialog --output-fd tested with stdout on the terminal, on a pipe and on a file: answer received in all three cases.
  - --run connection-test still works.
  - Not checked: the menu on the production server's own terminal emulator; the full test suite of the repository.
- Action required: none beyond installing dialog and postgresql-client as before (apt install dialog postgresql-client). If the error persists, send the output of: echo $TERM; tty; ls -l $(tty); and the exact command line used.

### 1.3.20261028.194152 - Terminal check, automatic configuration file, dialog install status

- Title: Clear message when the menu has no terminal; configuration file created when missing.
- Reason: Running the menu without an interactive terminal failed with "cannot open tty-output", which does not say what to do. A missing configuration file had to be written by hand.
- Changes:
  - New function check_tty: the menu checks that /dev/tty can be opened before starting dialog, and exits with code 3 and a bilingual message otherwise (suggests ssh -t or --run NAME).
  - New function print_config_template and write_config_template: when no configuration file is found, ~/.odoo-sql-maint.conf is created with a commented template and mode 600. An existing file is never overwritten.
  - With --config FILE: a missing file is created at that path (its folder too); an unreadable one is still an error (exit 2).
  - PG_DATABASE is empty in the template, so no database is targeted by mistake; the program asks for it.
  - Files: odoo-sql-maint, doc/odoo-sql-maint.conf.example (same content as the template written by the program).
- Bugs fixed:
  - Symptom: "cannot open tty-output" when the menu runs without an interactive terminal (ex. over a non-interactive session).
  - Diagnosis: dialog needs /dev/tty to draw its screens; without it, it fails with that message.
  - Fix: the menu checks /dev/tty first and explains the problem. The menu itself needs a terminal: use ssh -t, or --run NAME for scripts.
- Safeguards and edge cases:
  - An existing configuration file is never replaced; a second run only reads it (tested).
  - The created file is mode 600 (it may later hold settings for the database).
  - A failed creation (ex. read-only folder) is reported and the program continues with its defaults; with --config it exits 2.
  - Passwords still come only from ~/.pgpass.
- Checks:
  - bash -n OK; shellcheck 0.11.0 no warning.
  - No config anywhere: file created with mode 600, read back, exit 4 (no database set, as expected).
  - Second run: file not overwritten.
  - --config to a missing file in a missing folder: created, exit 0.
  - --config in an unwritable path: message, exit 2.
  - Menu without terminal with dialog present: message in French and English, exit 3.
  - Not checked here: the menu on a real terminal (dialog is not installed in this environment).
- Action required: install dialog on the server as root (apt install dialog postgresql-client), then run the menu from a real terminal (ssh -t) and set PG_DATABASE in the created file.

### 1.2.20261028.181641 - Program section in CHANGELOG, --changelog shows only this program, closed-pipe fix

- Title: odoo-sql-maint 1.2: own changelog section, closed pipe handled, repository integration.
- Reason: The program was delivered as a standalone file. The repository keeps one section per program in CHANGELOG.md and the --changelog option must show only the program's own section. The first release also claimed a clean exit on a closed pipe, which was not true.
- Changes:
  - `odoo-sql-maint` now lives at the root of the repository, with the repository's AGPL header and English code comments.
  - `--changelog` reads only the `## odoo-sql-maint` section of CHANGELOG.md, colours the version numbers, and removes colours when the output is redirected.
  - Configuration template moved to `doc/odoo-sql-maint.conf.example` (copied to /etc/default by the administrator, as for other programs).
  - Help text states the config files read and the key options in French and English.
  - Files: odoo-sql-maint, doc/odoo-sql-maint.conf.example, CHANGELOG.md.
- Bugs fixed:
  - Symptom: `odoo-sql-maint --list | head -2` printed "printf: write error: Broken pipe" on stderr.
  - Diagnosis: the SIGPIPE trap did not fire in this environment, so the builtin printf reported the error itself.
  - Fix: the list and changelog outputs ignore write errors on a closed pipe and exit with status 0.
  - Symptom: the output of `--changelog` included the sections of other programs.
  - Diagnosis: the program printed the whole CHANGELOG.md file.
  - Fix: only the section titled `## odoo-sql-maint` is printed.
- Safeguards and edge cases:
  - Destructive queries (push-purge, vapid-neutralize) still require confirmation, and are refused on names matching PROD_PATTERN unless --yes is given. Dry runs are always allowed.
  - Database names are checked against a strict pattern. Query text is fixed in the script and never built from user input.
  - Unknown options, missing values, unknown languages and unreadable config files produce a clear message and a non-zero exit code.
  - When CHANGELOG.md is missing, --changelog reports it on stderr and exits 2. When the file exists but has no section for this program, --changelog prints nothing.
- Checks:
  - bash -n and shellcheck 0.11.0: no warning.
  - --version, --list, --help, --changelog (also piped to head), --bogus (exit 2), --run push-purge --database odoo_prod (refused, exit 4), --run connection-test with no database (refused, exit 4).
  - Not checked here: menu mode (dialog not installed in the test environment) and live SQL (no test database reachable).
- Action required: install dialog (apt install dialog) and test the menu on DEV before using it on PROD. Copy doc/odoo-sql-maint.conf.example to /etc/default/odoo-sql-maint.conf and set PG_DATABASE.

### 1.1.20261028.085627 - Remove unused colour variable (shellcheck)

- Title: Remove unused colour variable (shellcheck SC2034).
- Reason: shellcheck reported a warning on the version 1.0 script.
- Changes: C_OK removed from the defaults and from init_colors. Files: odoo-sql-maint.
- Bugs fixed: symptom: shellcheck exit code 1. Diagnosis: C_OK was never printed. Fix: variable removed; output colours unchanged.
- Safeguards and edge cases: no behaviour change.
- Checks: bash -n OK, shellcheck OK, --version, --list, --changelog, prod guard.
- Action required: none.

### 1.0.20261028.085000 - Initial release: menu-driven SQL maintenance runner

- Title: Initial release of odoo-sql-maint.
- Reason: run maintenance SQL queries (VAPID keys and push subscriptions after copying PROD to DEV) from an interactive menu, or from maintenance scripts.
- Changes: menu mode (dialog), CLI mode (--run, --list), dry run (transaction rolled back), configuration from /etc/default and ~/.odoo-sql-maint.conf, audit log (LOG_FILE), French and English interface.
- Bugs fixed: none (first release).
- Safeguards and edge cases: confirmation for destructive queries, PROD_PATTERN guard, input validation, passwords read from ~/.pgpass only.
- Checks: bash -n OK, --version, --help, --list, --changelog.
- Action required: none for the first release; see 1.2.


## app-health-check.py

### 2.33.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: the regex that colours the "Summary: N failures" line still searched for "failure(s)", so the summary lost its colour. Diagnosis: test_couleurs_en_terminal_seulement failed. Fix: the regex searches for "failures".
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

### 2.32.20261029.195500 - --json, --changes, alerts by ntfy or webhook

- Title: machine-readable results, changes since the previous run, and alerts only when something happens.
- Reason: the report is a text for people. A cron job or a monitoring tool needs the results in a structured form, and an operator who runs the check every day wants to know what is new instead of reading every line again. Alerts by e-mail or Discuss are sent at every run, so the noise hides real problems.
- Changes:
  - --json: the results (label, status OK / FAIL / SKIP, detail), the number of failures and the changes are printed as JSON on standard output. The readable text of the checks goes to standard error during the run (sys.stdout is redirected, restored before the JSON).
  - --changes: the readable report gets a section listing the new failures and the resolved checks since the previous run.
  - Memory of the runs (state_path, save_run): the results of every run are saved in last-run.json, mode 600 (the details name hosts and certificates). Folder: APP_HEALTH_CHECK_STATE_DIR if set; else /var/lib/app-health-check when it exists or when running as root; else ~/.local/state/app-health-check. Written through a temporary file then replaced.
  - compare_runs: a check failing now and not failing before (new check included) is a new failure; a check passing now and failing before is resolved.
  - Alerts (send_alerts): NOTIFY_NTFY_URL (ntfy topic) and NOTIFY_WEBHOOK_URL (JSON title and message), sent only when there is a failure or a change. Other keys and the e-mail / Discuss behaviour are unchanged.
  - Files touched: app-health-check.py, lang/app-health-check.fr.po, doc/en and doc/fr app-health-check.conf.example.
- Bugs fixed: none.
- Safeguards and edge cases:
  - No previous run: no change is reported (first run, unreadable or damaged file).
  - A failed save is reported on standard error ([ATTN]), the check is not stopped.
  - Notification URLs must start with http:// or https://; others are refused with a message.
  - A notification error is reported and does not change the exit code (1 only for failed checks).
  - The ntfy title is ASCII (HTTP headers): the accents of the subject are replaced.
- Checks:
  - py_compile OK; --version displays the dynamic version; --help lists --changes and --json.
  - Unit checks on the comparison, the saved file (mode 600) and its reading, done by hand before the commit.
- Action required: none. To receive alerts, set NOTIFY_NTFY_URL or NOTIFY_WEBHOOK_URL in the configuration file, and use --changes or --json in the cron job if wanted.

### 2.31.20261028.214122 - --menu: English programs translate the menu and its help through their catalogue

- Title: --menu: English programs translate the menu and its help through their catalogue.
- Reason: With --lang en, the --menu help and the menu entries were partly in French: the catalogue tests (test_i18n) and the English help test (test_web_monitor) failed.
- Changes:
  - The menu entries and the --menu help are written in English in the code; their French text is in lang/app-health-check.py.fr.po (msgid = English text, msgstr = French).
  - apps/_menu.py: menu() takes traduire (the program's translator) and langue (the program's display language). The menu labels and its messages follow the program's language, not only NGINX_TOOLS_I18N_LANGUE.
  - nginx-tools-tests/test_config_defaut.py: --menu is an action (CLI only, like --backup), excluded from the check of the configuration model.
  - Files: app-health-check.py, lang/app-health-check.py.fr.po, apps/_menu.py, nginx-tools-tests/test_config_defaut.py, CHANGELOG.md.
- Bugs fixed: symptom: test_i18n reported French text in the code of this English program. Diagnosis: the new menu strings were French in the code, but this program's code is English and its texts are translated through lang/. Correction: English strings plus catalogue entries.
- Safeguards and edge cases: the menu labels, its confirmation and cancel messages follow the language of the program; the entries still run the same options as before.
- Checks: test_i18n (catalogues), test_menu, test_config_defaut, the English help test of this program where it exists.
- Action required: none.

### 2.30.20261028.211449 - --menu: interactive menu of the usual operations

- Title: New option --menu: a menu (dialog when installed, text otherwise) for the usual operations of app-health-check.py.
- Reason: Operations were only reachable through command-line options. The menu offers them by number, shows the configuration read, and asks for confirmation before operations that change the system.
- Changes:
  - New option --menu (terminal required). Entries: vérification de la santé, courriel des alertes, courriel de test; configuration read (c or the menu item); change log (--changelog); quit.
  - Each entry runs this program again with the options received on the command line (except --menu) plus its own option. Entries that change the system ask for confirmation first.
  - Shared library apps/_menu.py (new): dialog when installed, text menu otherwise, with a note to install dialog.
  - Help: --menu listed in alphabetical order. --help, --version and --changelog keep their priority over --menu.
  - Files: app-health-check.py, apps/_menu.py (new), nginx-tools-tests/test_menu.py (new), CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - Without a terminal, --menu refuses with an error and exit code 1; nothing is run.
  - The menu relaunches the program only; root checks, locks and confirmations stay those of the operation itself.
- Checks:
  - test_menu: --menu listed in the help, refused without a terminal.
  - Manual test in a pseudo-terminal (text menu and stand-in dialog) on read-only entries.
  - Other tests of the program and conventions: see the pull request.
- Action required: none. To get the graphical menu: sudo apt install dialog.

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

### 2.28.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: none.
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

### 2.27.20261028.214122 - --menu: English programs translate the menu and its help through their catalogue

- Title: --menu: English programs translate the menu and its help through their catalogue.
- Reason: With --lang en, the --menu help and the menu entries were partly in French: the catalogue tests (test_i18n) and the English help test (test_web_monitor) failed.
- Changes:
  - The menu entries and the --menu help are written in English in the code; their French text is in lang/app-log-check.py.fr.po (msgid = English text, msgstr = French).
  - apps/_menu.py: menu() takes traduire (the program's translator) and langue (the program's display language). The menu labels and its messages follow the program's language, not only NGINX_TOOLS_I18N_LANGUE.
  - nginx-tools-tests/test_config_defaut.py: --menu is an action (CLI only, like --backup), excluded from the check of the configuration model.
  - Files: app-log-check.py, lang/app-log-check.py.fr.po, apps/_menu.py, nginx-tools-tests/test_config_defaut.py, CHANGELOG.md.
- Bugs fixed: symptom: test_i18n reported French text in the code of this English program. Diagnosis: the new menu strings were French in the code, but this program's code is English and its texts are translated through lang/. Correction: English strings plus catalogue entries.
- Safeguards and edge cases: the menu labels, its confirmation and cancel messages follow the language of the program; the entries still run the same options as before.
- Checks: test_i18n (catalogues), test_menu, test_config_defaut, the English help test of this program where it exists.
- Action required: none.

### 2.26.20261028.211449 - --menu: interactive menu of the usual operations

- Title: New option --menu: a menu (dialog when installed, text otherwise) for the usual operations of app-log-check.py.
- Reason: Operations were only reachable through command-line options. The menu offers them by number, shows the configuration read, and asks for confirmation before operations that change the system.
- Changes:
  - New option --menu (terminal required). Entries: analyse des journaux, par heure et par jour, détail des erreurs; configuration read (c or the menu item); change log (--changelog); quit.
  - Each entry runs this program again with the options received on the command line (except --menu) plus its own option. Entries that change the system ask for confirmation first.
  - Shared library apps/_menu.py (new): dialog when installed, text menu otherwise, with a note to install dialog.
  - Help: --menu listed in alphabetical order. --help, --version and --changelog keep their priority over --menu.
  - Files: app-log-check.py, apps/_menu.py (new), nginx-tools-tests/test_menu.py (new), CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - Without a terminal, --menu refuses with an error and exit code 1; nothing is run.
  - The menu relaunches the program only; root checks, locks and confirmations stay those of the operation itself.
- Checks:
  - test_menu: --menu listed in the help, refused without a terminal.
  - Manual test in a pseudo-terminal (text menu and stand-in dialog) on read-only entries.
  - Other tests of the program and conventions: see the pull request.
- Action required: none. To get the graphical menu: sudo apt install dialog.

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

### 1.146.20261101.140404 - Hundredths for the times, three kinds of 404 in the status bar, full-width Odoo warnings, --days for --log-chk-sitemap

- Title: response times to the hundredth (5 columns instead of 6), three 404 counters in the status bar (404s, 404b, 404o), warnings of Odoo on the whole width, and --days honoured by --log-chk-sitemap.
- Reason: the user's review of 1.145: (1) the times are shown to the hundredth and the column is 2 characters narrower; (2) the 404s must be told apart: 404s (page of the sitemap), 404b (blocked by our programs), and the others; their details are shown with Ctrl-G and Ctrl-T; (3) the Odoo warnings and errors (CSRF, for example) must use the whole width ($COLUMNS) instead of being cut at $COLUMNS - 10; (4) "--log-chk-sitemap --days 1" did not limit the report: all 110 files were read.
- Changes:
  - hundredths(): a SQL or Python time is shown to the hundredth (0.046 -> 0.05); above 100 s, one decimal as before (short_time rule). Used by aligned_request (Odoo lines) and aligned_nginx_request (merged lines).
  - Time columns: 5 characters each (was 6). NUMBERS_BLOCK_WIDTH 40 -> 38, so the GET column and the text of the lines without a request stay aligned. The websocket duration uses 11 columns (was 13). The header label "PY s" moved from column 26 to 25 (column_header).
  - StatusBar.pieces_404(): "404s" (gone: a page of the sitemap, counted in the health), "404b" (refused on purpose by --disable-uri, not in the health), "404o" (other URL never in the sitemap, not in the health). Shown after the 4xx group.
  - Dashboard (Ctrl-G, Ctrl-T): the URL details are also listed for 404o and 404b (the 404s already were).
  - WARN_START_RE and WARN_CONT_RE: an Odoo message without structure ("07:00:13.24 root WARN odoo.http ...") starts a warning, and its continuation lines ("07:00:13.24 root: ...") stay in it. While the warning is on, the stream line is shortened at $COLUMNS - 1 instead of $COLUMNS - 10 (Output.write, wide=True), unless --no-truncate. Structured WARNING, ERROR and CRITICAL lines are included.
  - sitemap_report(url, folder, days): --days N keeps only the nginx lines of the last N days (their own time, NGINX_TIME_RE) and skips the files last written before that day. The report shows the period ("Period: the last N days", or "the whole nginx logs").
  - Files: app-log-live.py, lang/app-log-live.fr.po (5 new strings), nginx-tools-tests/test_app_log_live.py (AppLogLive146, and expectations of the time columns updated in several tests).
- Bugs fixed:
  - symptom: "--log-chk-sitemap --days 1" reads all the logs ("Fichiers lus : 110"). Diagnosis: main() called sitemap_report() without the value of --days. Fix: days parameter, file filter by modification time and line filter by the time of the line.
  - symptom: 404 on "/" counted as an error of the sitemap. Diagnosis: "/" is a page of the sitemap, so any 404 on it is counted as important, even when the client is a bot. Not changed in this version: see Action required.
- Safeguards and edge cases: a line without a readable time is kept (the period is not applied to it). A file of rotated logs written before the period is not opened. Without --days, the report is unchanged. A time of 100 s or more keeps the one decimal of 1.144. The websocket duration keeps its three decimals (it is not a response time). The warning width applies only with the full-width rule of the stream (--truncate 0 or automatic); --no-truncate is unchanged.
- Checks performed: py_compile; --help runs; testeur on test_app_log_live and test_i18n: 237 tests, 235 pass, 2 failures already present before 1.141 (test_colonnes_jamais_tassees_pays_noms_anonymises_et_souligne_tous_les_n, test_120_journal_html_un_fichier_par_jour); AppLogLive146 (3 tests: hundredths, the three 404 counters and the health, the warning regexes) pass; the --days filter of the report was not run against real logs (no nginx log in the test environment).
- Action required:
  1. Restart app-log-live.py to load 1.146. Odoo warnings now take the whole width: tell me if a line is still cut.
  2. Not done in this version, waiting for your answer: (a) header PAY, IP and ISP labels and the 5-character narrower IP block (which column exactly: the address block of 18 characters, or the name column); (b) the "h" key that shows the startup legend (currently "h" opens the help menu; should "h" show the legend, and should "?" keep the menu?).
  3. 404 on "/": send me one or two nginx lines of this 404 (IP, Host, User-Agent). If the IP is banned at that time, I can exclude the 404s of banned addresses from the sitemap report; say so, because the logs do not record bans.

### 1.145.20261101.122458 - Status bar when the health moves; wider merge windows; host= hidden by default (--display-host); websockets are never slow

- Title: the status bar also appears when the health moves by more than 3 points; pairs of lines are merged over a wider window; the host= of the nginx lines is hidden unless --display-host (key k); a websocket duration is no longer a slowness.
- Reason: the user's review of the dashboard: (1) the bar should come more often when the health changes by more than 3 points, and stay at 2/3 of $LINES otherwise, without two bars in the first 10 lines; (2) pairs of lines were still not merged; (3) the Cloudflare visitors cannot be banned from the relay address; (4) an option to show host= at the end of the line, hidden by default; (5) a websocket (chat) is not a slow connection.
- Changes:
  - status_bar_due(): the bar is written after `every` displayed lines (2/3 of the terminal height by default), or sooner when the health moved by more than BAR_CHANGE_POINTS (3) since the last bar, provided BAR_MIN_GAP (10) lines have passed. The last bar is kept in state["bar_at"] and state["bar_health"].
  - startup_status_bar(): sets the baseline, so the periodic bar does not come again within the first lines.
  - MERGE_WINDOW 2.0 -> 5.0 s (log time) and MERGE_HOLD 3.0 -> 8.0 s (wall clock). An nginx-only line (no Odoo partner) can now show up to 8 s later when the stream is idle.
  - --display-host (configuration DISPLAY_HOST, menu key k, Formatting.display_host): the host="..." of an nginx line is removed from the line unless this option is on (HOST_TEXT_RE, same cut as the User-Agent).
  - LONG_CONNECTION_RE: request_duration() returns None for /websocket and /longpolling; a merged websocket line gets no slowness marker. The colour of its duration (transfer_style) is kept.
  - Files: app-log-live.py, lang/app-log-live.fr.po (2 new strings), nginx-tools-tests/test_app_log_live.py (class AppLogLive145).
- Bugs fixed: symptom: a second status bar within the first 10 lines at start; diagnosis: the bar written after the history and the periodic bar every 2/3 of the lines were not coordinated; fix: the baseline above. symptom: an nginx line shown alone, then its Odoo line shown alone a moment later (same URL, status 200, 0.24 s apart in the log); diagnosis: the Odoo journal is read more slowly, so the nginx line was released (2 s of log time or 3 s of wall clock) before its partner came; fix: the wider windows. symptom: "lente : 2186.2 s" on a websocket; diagnosis: a websocket is a connection kept open, its duration is not a request time; fix: LONG_CONNECTION_RE.
- Safeguards and edge cases: the status bar health rule needs a previous bar: the first bar is at 2/3 of the lines. The two constants can be changed in one place. A pair with a different status (nginx 304, Odoo 200 for another request, for example a service worker fetch) is still NOT merged: they are two requests. Without --display-host the host is not shown; the 404 sitemap tag stays at the end of the line. The Cloudflare relay (CF-Connecting-IP) is not handled here: nginx bans by $remote_addr, so the client address needs nginx real_ip configuration (not in this version).
- Checks performed: py_compile; --help shows --display-host; rendering with and without display_host; websocket with a 6000.5 s duration: no slowness marker and request_duration None; merge of an nginx line and an Odoo line 4.2 s later (one line); status_bar_due reviewed for the 2/3 rule, the 3-point rule, the 10-line minimum and the missing-baseline case; test_i18n OK. test_app_log_live: 2 failures, both already present before 1.141 (test_colonnes_jamais_tassees..., test_120_journal_html...).
- Action required: restart app-log-live.py. Press k to show the host, or add DISPLAY_HOST=yes in the configuration file. If the pairs are still split, tell me the time gap between the two lines.

### 1.144.20261101.120235 - Ban suggestions: no CDN relays, no sweep web-monitor.py does not recommend; sitemap tag at the end of the line; times over 100 s with one decimal

- Title: the dashboard no longer proposes to ban a shared relay (Cloudflare) or an address that a fresh web-monitor.py run judged harmless; the sitemap tag moves to the end of the line; long durations show one decimal.
- Reason: the user's dashboard proposed five addresses to ban (Cloudflare edge addresses among them) with 404 counts of 5 to 8 pages, while web-monitor.py scores them 0/7, 1/7 and 3/7 (its investigation score). The user asked to remove the new column before OS and to put the sitemap tag at the end of the line, and to show durations over 100 s with one decimal (2186.246226 becomes 2186.2).
- Changes:
  - CDN_NAME_RE: an address whose name (DNS or RDAP) names a CDN or relay (cloudflare, akamai, fastly, incapsula, imperva, bunnycdn) is never proposed for a ban, neither by the 404 sweep nor by web-monitor.py.
  - Stats.to_ban(): a 404 sweep is proposed only when the last run of web-monitor.py is fresh (less than 48 h, Stats.reco_loaded) and recommends it; without a fresh run, the rule is unchanged (5 different pages in 404).
  - Stats.not_proposed: the addresses held back and the reason; the dashboard shows them on the line "Not proposed for banning".
  - Sitemap tag ([in sitemap.xml], [not in sitemap.xml], [disabled], [not read yet]) moved to the END of the 404 line (sitemap_tag() replaces sitemap_cell()). The column before OS, its header label SITEMAP and the padding are removed. The RL column (--request-length) is unchanged.
  - short_time(): a duration over 100 s is shown with one decimal (2186.246226 becomes 2186.2), in the SQL time, the Python time and the websocket duration columns; other values are unchanged.
  - Files: app-log-live.py, lang/app-log-live.fr.po (SITEMAP label removed, new strings), nginx-tools-tests/test_app_log_live.py (class AppLogLive144; tests 142 and 143 updated for the tag at the end of the line).
- Bugs fixed: symptom: the dashboard proposed banning Cloudflare edge addresses and addresses that web-monitor.py scores 0/7 to 3/7. Diagnosis: to_ban() took any address with 5 different 404 pages, and the relay of many visitors and the web-monitor.py judgement were not consulted. Fix: the relay exclusion and the fresh-run rule above.
- Safeguards and edge cases: banning a Cloudflare address would block every visitor who goes through it, so relays are never proposed, even when web-monitor.py recommends them (they are named in "Not proposed for banning"). Without a web-monitor.py run from the last 48 h, the 404 sweep rule is the old one: run web-monitor.py so that its judgement is used. The web-monitor.py score (x/7) is not read by this program, only its recommendation list. A duration of exactly 100 s keeps three decimals.
- Checks performed: py_compile; rendering of 404 lines (tag at the end, nothing before OS), werkzeug line, websocket line (2186.2); short_time on 2186.246226, 12.345678, 100.000, empty and text values; test classes AppLogLive142, AppLogLive143 and AppLogLive144 (relays never proposed, sweep held without a recommendation, recommended address proposed, rule unchanged without a fresh file); test_i18n OK. test_app_log_live: 2 failures, both already present before 1.141 (test_colonnes_jamais_tassees..., test_120_journal_html...).
- Action required: restart app-log-live.py. Run web-monitor.py so that its judgement is available for the 404 sweeps. To ban the real visitors behind Cloudflare, the ban must use the client address (CF-Connecting-IP), which this version does not do.

### 1.143.20261101.111357 - Sitemap on by default, refused paths tagged [disabled], merge of encoded URLs and websockets, status bar at 80 %, --log-chk-sitemap

- Title: the sitemap check is on by default; the tag column shows the paths refused on purpose; the merge of the same request now works with different URL encodings and for websockets; the status bar is 80 % of the width; f re-reads the window size; new report option --log-chk-sitemap.
- Reason: the user's checks of 1.142 and a live log: (1) the sitemap is always checked by default (https://www.rencontres-linux.quebec/sitemap.xml) unless --sitemap gives another one; (2) the tag [disabled] means a URL refused on purpose by our configuration, not a sitemap state; (3) only a 404 on a page listed in the sitemap lowers the health percentage; (4) some request lines were still not merged; (5) after f, the window size must be read again and the status bar shown; the status bar must be 80 % of the width like the underlined lines; (6) a report of the 404 pages listed in the sitemap is wanted.
- Changes:
  - DEFAULT_SITEMAP_URL: the sitemap is read at start unless --no-sitemap (config key NO_SITEMAP) or --sitemap URL (config key SITEMAP) gives another address. Environment APP_LOG_LIVE_SITEMAP=off turns the default off (used by the tests and by servers without network).
  - disabled_uri_re(), is_disabled(): the paths of /etc/nginx/snippets/uri-desactivees.conf ("# uri : CHEMIN" lines written by nginx-hardening.sh --disable-uri) with the same rule as the nginx location (optional language prefix, then the path and "/" or the end).
  - Tag [disabled] / [désactivé] for those 404 answers, before any sitemap test. Tag [not read yet] / [pas encore lu] while the sitemap is not read (replaces the 1.142 label [disabled] for that case).
  - Counting: a refused path is counted apart (disabled_404) and is never a penalty, neither in the health percentage nor in the indicators. Only a listed page (gone_404) lowers the percentage; other URLs (unknown_404) do not.
  - request_key(): the URL is decoded on both sides (nginx keeps %20 and %C3%A9 of the client, Odoo's log may show the characters).
  - is_odoo_request(): a websocket line (one duration, no SQL count) is merged with its nginx 101 line.
  - status_line(): width is 80 % of the terminal columns (UNDERLINE_RATIO), like the underlined lines.
  - f key: reload_terminal_size() reads the window size again (os.get_terminal_size on stdout, stderr, stdin; sets COLUMNS and LINES); if the width changed, the labels are shown again at the next request line and the form width is recomputed; the status bar is written after the refreshed lines.
  - --log-chk-sitemap [--sitemap URL]: sitemap_report() reads the nginx access logs (access.log and rotated/gzipped files) and lists the 404 answers by page (language prefix and query string removed): pages in the sitemap (important), refused on purpose, and never in the sitemap (attacks, top 10). Exit 0, or 2 when the sitemap or the logs cannot be read. It exits without the stream, like --rate-limit.
  - Stats.health(): an informative line for the 404 refused on purpose.
  - Files: app-log-live.py, lang/app-log-live.fr.po (new strings, help texts), nginx-tools-tests/test_app_log_live.py (class AppLogLive143; module sets APP_LOG_LIVE_SITEMAP=off for its subprocesses), CHANGELOG.md.
- Bugs fixed: symptom: lines of the same request were shown twice (Odoo line with its SQL counts, nginx line alone), for example image URLs with spaces, parentheses or accents, and websocket lines; diagnosis: the key compared the raw URL, and nginx keeps the client encoding (%20, %C3%A9) while Odoo's line shows the characters; a websocket Odoo line has no SQL count and was never a merge candidate; fix: decoded keys on both sides, and websocket lines are merge candidates. symptom: after a window resize, f kept the old width and the status bar was not shown again (reported by the user); diagnosis: $COLUMNS and $LINES were read once at start; fix: reload_terminal_size() on f, then the status bar.
- Safeguards and edge cases: a missing or unreadable uri-desactivees.conf means no refused path (no error). A sitemap that cannot be read keeps the last good list (warning in the health). The refused paths are tagged even when the sitemap is not read. A URL both refused on purpose and listed in the sitemap is tagged [disabled] (our configuration refuses it on purpose), and not counted: a listed page that is refused on purpose stays visible in the report of --log-chk-sitemap. --log-chk-sitemap reads the logs of /var/log/nginx; a file that cannot be read is skipped. Queries are dropped in the report, so /page?a=1 and /page are one page.
- Checks performed: py_compile; --version and --help (new options sorted by the help formatter); merge of the nginx and Odoo lines of the user's examples with %20, raw spaces, %C3%A9 and accents (one line each); websocket merge with the real line format (101 494 1730.555); tag and counting with a refused path (/shop/panier, uri : /shop); report on a sample access log with a patched sitemap read (?query and language prefix counted on one page; attacks listed apart; unreadable sitemap: code 2); test class AppLogLive143; test_i18n OK. test_app_log_live: 2 failures, both already present before 1.141 (test_colonnes_jamais_tassees..., test_120_journal_html...).
- Action required: none for the defaults (the sitemap of https://www.rencontres-linux.quebec/sitemap.xml is now read at start; use --no-sitemap to turn it off). Restart app-log-live.py. Run app-log-live.py --log-chk-sitemap on the server to see the 404 pages in the sitemap.

### 1.142.20261101.103302 - Sitemap check of the 404 pages: --sitemap URL, two 404 counters, tag before the OS column

- Title: pages 404 listed in the Odoo sitemap.xml are counted in the health (important pages that no longer exist); the other 404 pages (never existed: attacks) are counted apart and do not lower the health; each 404 line shows whether its page is in the sitemap.
- Reason: the user wants the 404 URLs that matter for SEO identified first, because they belong to the sitemap.xml of Odoo. The URLs that never existed (probes, attacks) must not change the health percentage.
- Changes:
  - Option --sitemap URL (configuration key SITEMAP). Class Sitemap: the file is read in a background thread (timeout 15 s), read again every hour, and again after 60 s while it fails. A sitemap index is followed (50 sitemaps at most). Only http and https addresses are accepted (otherwise the program stops with a message).
  - sitemap_path(): the path compared with the sitemap has no scheme, host, query or fragment, no language prefix (/fr_CA/, /en/) and no trailing slash. The same rule is applied to the sitemap and to the 404 URLs.
  - sitemap_cell(): tag column of SITEMAP_WIDTH (22) characters, placed after the RL column and before the OS column. 404 lines: [in sitemap.xml] (orange, counted in the health) or [not in sitemap.xml] (grey, not counted); [disabled] (grey) while the sitemap is not read yet. Other lines: blank. French: [dans sitemap.xml], [pas dans sitemap.xml], [désactivé].
  - Stats.observe(): a 404 is counted in gone_404 (URL listed) or unknown_404 (URL not listed) once the sitemap is read.
  - Stats.health(): two indicators. "404 on pages of sitemap.xml" (counted: warning from 1 page, alert from 5). "404 on URLs never in sitemap.xml" (informative, never changes the state). The score takes 0.1 point per 4xx as before, except the unknown 404 pages.
  - column_header(): label SITEMAP over the tag column, RL label before it when --request-length is given. The Odoo message text keeps its column (the tag column is counted in its padding).
  - Files: app-log-live.py, lang/app-log-live.fr.po (9 new entries), nginx-tools-tests/test_app_log_live.py (class AppLogLive142).
- Bugs fixed: none (new feature).
- Safeguards and edge cases: without --sitemap the layout, the counters and the score are unchanged. A network, HTTP or XML error keeps the last good list and shows the reason in the health (warning). A sitemap larger than 50 MB is refused. Comparison ignores the query string, so /page?x=1 is the page /page. A first path segment of two letters (/ab/) is taken for a language prefix on both sides, so such a page is compared without it. The sitemap is read in a thread, so a slow server never blocks the stream.
- Checks performed: py_compile; --version; rendering of 404 and 200 lines with the sitemap off, on, with --request-length and with --min; alignment of the header labels (RL, SITEMAP, OS) on the rendered lines; test class AppLogLive142 (8 tests) OK; test_i18n OK; test_app_log_live: 2 failures, both already present before 1.141 (test_colonnes_jamais_tassees..., test_120_journal_html...), not touched by this version.
- Action required: to enable the check, add --sitemap https://www.rencontres-linux.quebec/sitemap.xml (or SITEMAP=... in the configuration file), then restart app-log-live.py. The tag [désactivé] is shown when the sitemap is not read yet (the address is wrong or unreachable).

### 1.141.20261031.232600 - Time colours: white under 1 s, green 1 to 3 s, yellow 3 to 6 s, red above 6 s; websocket durations coloured

- Title: the traffic light of the times follows the thresholds given by the user; the duration of a websocket (no SQL time) is coloured too.
- Reason: the thresholds of 1.139 (green 1 to 3 s, yellow above 3 s) were not the ones wanted: green 1 to 2 s, yellow 3 to 6 s, red above 6 s. A websocket line (4035.985 s) was not coloured at all.
- Changes:
  - transfer_style(): under 1 s none (white); from 1 s to under 3 s green (transfer_low, 32); from 3 s to 6 s yellow (transfer_mid, 33); above 6 s red (transfer_slow, 1;31). The gap between 2 and 3 s is green.
  - Werkzeug lines: the time column is coloured when it has a value, with SQL time or without (websocket: duration in the last column).
  - Merged lines: the total is SQL time + Python time, or the Python time alone when there is no SQL time.
  - nginx-tools-tests/test_app_log_live.py: expected colour of the 5.5 s request (yellow now).
- Bugs fixed: symptom: the websocket duration was not coloured; a first version of this change showed the raw value (6 decimals): the shown text is coloured now.
  symptom: websocket duration never coloured; diagnosis: the colour required an SQL time, which a websocket line does not have; fix: the condition is the value of the Python time.
- Safeguards and edge cases: a non-numeric value is not coloured (the test is on the value of the time column only). Thresholds are fixed; say if they must be options.
- Checks performed: py_compile; --version; transfer_style at 0.5, 1.5, 2.9, 3, 5.9, 6, 6.1 and 4035.985; test_requetes_lentes_surlignees_avec_leur_duree_et_slow; test_app_log_live: 218 tests, 2 failures, both already present before 1.141 (test_colonnes_jamais_tassees..., test_120_journal_html...); test_logs_merge and test_i18n OK.
- Action required: none. Restart app-log-live.py.

### 1.140.20261031.231025 - Fix crash on a POST line in the header; header never stops the stream

- Title: a crash (ValueError) when the first request line shown was a POST: the header was measured on the line itself, which has no "GET"; it stopped app-log-live.
- Reason: the user's run stopped with a Python traceback at the first request line (line 6539, emit -> paint -> show_header -> column_header).
- Changes:
  - column_header(): the offsets of the labels are always taken from a GET sample rendered with the same options; the line given is used only for the fields (DATE, PROG, LEVEL, ADDRESS/NAME) and for the start of the numbers block ("H1.1").
  - paint(): a failure while printing the header is caught (ValueError, IndexError, KeyError): the header is then not shown for that line and the stream goes on.
- Bugs fixed: symptom: traceback "substring not found" at the first POST line, program stopped; diagnosis: plain.index("GET") on a POST line; fix: sample offsets and the guard.
- Safeguards and edge cases: any other line form without "H1.1" gets no header. The guard does not hide programming errors elsewhere in the stream.
- Checks performed: py_compile; --version; header of a POST line rendered with --min (fields and labels aligned); test_app_log_live: 218 tests, 2 failures, both already present before 1.140 (test_colonnes_jamais_tassees..., test_120_journal_html...); test_logs_merge and test_i18n OK.
- Action required: none. Restart app-log-live.py.

### 1.139.20261031.230500 - Header labels on the real fields of the line; times from 1 s in green

- Title: the labels DATE, PROG, LEVEL and ADDRESS/NAME are placed on the fields of the first real request line, so they follow the options (--min, names, width); the times from 1 s are green (white under 1 s, red from 3 s).
- Reason: 1) the four first labels were not aligned with the fields. 2) the times from 1 s must be green (yellow of 1.134 removed; if another colour from 1 s is wanted, say so).
- Changes:
  - line_fields(plain): column of DATE, PROG (program), LEVEL and ADDRESS/NAME in a rendered line.
  - column_header(..., plain=None): the four labels are written at those columns; a label that would overlap another one or the numbers block is left out. Without a line, a sample rendered with the same options is used.
  - show_header(plain): measured on the line being displayed (start = "H1.1" of that line).
  - After a change of --min or --request-length (keys m and j) the header is printed again at the next request line, measured on it.
  - transfer_style(): under 1 s white; 1 to 3 s green (STYLES transfer_mid = 32); from 3 s red.
- Bugs fixed: symptom: the first labels not above their fields; diagnosis: they were placed at fixed offsets of a sample line rendered with other options; fix: measured on the real line.
- Safeguards and edge cases: a line without DATE, PROG or LEVEL (non-Odoo, nginx variants) has fewer labels. The header is cut to the terminal width.
- Checks performed: py_compile; --version; check of the label columns against the fields of rendered lines (--min and --request-length on and off); test_i18n (32 tests OK); test_app_log_live: 186 tests, 2 failures, both already present before 1.139 (test_colonnes_jamais_tassees..., test_120_journal_html...); test_logs_merge OK.
- Action required: none. Restart app-log-live.py.

### 1.138.20261031.225800 - Column header on one line; start-up legend removed

- Title: the column header is ONE line: DATE, PROG, LEVEL and ADDRESS/NAME for the first columns, then the labels above the request columns (HTTP, STA, SIZE, SQL, SQL s, PY s, RL, OS, REQUEST).
- Reason: the header was shown on two lines (a legend "Colonnes : ..." then the labels), and the labels did not say what the first columns are.
- Changes:
  - column_header(): builds one line; the four labels of the first columns are written at the start of the line when they fit before the numbers block (no alignment with the fields of the line, which vary); the request labels stay above their columns.
  - The start-up legend line (stderr) is removed.
  - lang/app-log-live.fr.po: entries for DATE, PROG, LEVEL (NIVEAU), ADDRESS/NAME (ADRESSE/NOM); the entry of the removed legend is removed (test_i18n).
- Bugs fixed: none (layout).
- Safeguards and edge cases: when the first labels would overlap the numbers block (a very narrow prefix), they are not written; the line is cut to the terminal width.
- Checks performed: py_compile; --version; rendering of the header (full, minimal, narrow); test_i18n (32 tests OK); test_app_log_live: 186 tests, 2 failures, both already present before 1.138 (test_colonnes_jamais_tassees..., test_120_journal_html...); test_logs_merge OK.
- Action required: none. Restart app-log-live.py.

### 1.137.20261031.222230 - Refresh (f) applies --min and --hide-addons; header before the first request line and cut to the terminal; times under 1 s in white

- Title: the refresh key f applies the current --min and --hide-addons; the column header is printed just before the first request line, measured on that line, and never wider than the terminal; the times under 1 s are white again (yellow from 1 s, red from 3 s).
- Reason: 1) after --hide-addons was switched on, f showed the addon lines again. 2) the header was printed at start-up, above the presence summary and the help, and its columns did not match the real lines (the sample prefix is not the real one, e.g. with --min). 3) the times under 1 s must stay white, as before.
- Changes:
  - refresh_lines(): the buffered lines discarded by the current --min (discard_in_min) or --hide-addons (discard_addons) are not displayed again.
  - column_header(request_length, minimal, width, columns, start): the start of the columns is the column of "H1.1" in the first real request line (paint(): show_header(at)); a sample is used only for the offsets and when no start is known. The header is cut to the terminal width (terminal_columns(), new). The header is written on stderr (the stream on stdout keeps its layout, and the tests that read the stream are unchanged), after flushing stdout, just before the first request line. It is printed again when --min or --request-length is switched (keys m and j).
  - transfer_style(): under 1 s returns None (no colour); the transfer_ok style is removed.
- Bugs fixed: symptom: lines hidden by --hide-addons shown again with f; diagnosis: refresh_lines() only applied the --only / highlight filter, the discards were done when reading; fix: same discards in refresh. Symptom: header not aligned with the lines, and printed far from the first line; diagnosis: measured on a sample line with other options; fix: measured on the first real request line.
- Safeguards and edge cases: no request line yet: no header. A terminal narrower than the labels: the labels beyond the width are not shown. Toggling --min or j re-prints the header with the sample offsets (the next real line is the reference only at the first display).
- Checks performed: py_compile; --version; rendering of the header (full, minimal, narrow) and of transfer_style(0.4 / 2 / 5); test_app_log_live: 218 tests, 2 failures, both already present before 1.137 (test_colonnes_jamais_tassees..., test_120_journal_html...); test_logs_merge and test_i18n OK.
- Action required: none. Restart app-log-live.py.

### 1.136.20261031.220401 - rl= in its own column (--request-length); column header at start; LIN in green, AND in cyan

- Title: the request length (rl=) of nginx lines leaves the end of the line for its own column before the GET, shown with --request-length (option and menu key j); a header labels the request columns at start-up; in the OS column LIN is green and AND is cyan.
- Reason: 1) rl= at the end of the line is not useful for every reader; a column is easier to scan. 2) the columns of the request lines are not labelled. 3) the two most common systems stand out at a glance.
- Changes:
  - --request-length (new option, configuration key REQUEST_LENGTH, default: not shown); Formatting(request_length=...); the column is RL_WIDTH (5) characters + 1 space before the OS; Odoo lines keep a blank in the same column; the NUMBERS block target of the Odoo texts grows by the same width.
  - rl= is removed from the end of the nginx lines in every case (shown in its column with the option).
  - column_header(): one line of labels (HTTP, STA, SIZE, SQL, SQL s, PY s, RL when shown, OS, REQUEST) placed on the columns of a sample Odoo request line; printed on stderr at start-up with a short legend line.
  - OS_COLORS: LIN green (32), AND cyan (36); other systems unchanged.
  - Menu key j ("reqlen") toggles --request-length; the configuration save (C) writes REQUEST_LENGTH when it changed.
  - lang/app-log-live.fr.po: entries for the header and the new texts.
- Bugs fixed: none (new features).
- Safeguards and edge cases: the header is on stderr, so a pipe of the stream (stdout) is unchanged. The start of the columns is measured on the sample, so the header follows changes of the date, host and name widths. An nginx line without rl= leaves the RL column blank. The colours of OS are added after the alignment is computed (no effect on the widths).
- Checks performed: py_compile; --version; rendering of the header and of nginx lines with and without the column (rl= moved, OS colours in the code); test_i18n (32 tests OK); test_app_log_live: 186 tests, 2 failures, both already present before 1.136 (test_colonnes_jamais_tassees..., test_120_journal_html...); test_logs_merge OK.
- Action required: none. Restart app-log-live.py. Use --request-length (or menu key j) to see rl=.

### 1.135.20261031.215149 - Menu key u for --hide-user-agent; Odoo line merged when it comes before its nginx line; periodic checks while the stream is busy

- Title: the menu gets the key u for --hide-user-agent; with --log-merge an Odoo request line that arrives before its nginx line is merged with it; the periodic checks (health alert, disk, connections, external IP) run while the stream is busy.
- Reason: 1) the last options must be reachable from the menu. 2) two lines of the same websocket request (21:33:15.00 nginx, 21:33:15.36 Odoo) were not merged: the Odoo line was shown alone and the nginx line came after it. 3) a health alert printed at 21:19:30 reported errors from 14:06:06: the alert covers the period "since" the previous check; the check had not run for hours.
- Changes:
  - MENU_KEYS: key u ("hideua"); the handler toggles options["hide_user_agent"] and the Formatting of the stream; the menu line "--hide-user-agent" is listed with its state; the configuration save (C) writes HIDE_USER_AGENT when it changed.
  - merge_step(): an Odoo request line with no nginx line waiting is HELD (MERGE_WINDOW in log time, MERGE_HOLD in wall-clock time, as the nginx lines); when its nginx line comes, the two are merged. Before, only the nginx line was held.
  - nginx-tools-tests/test_app_log_live.py: test_requete_differente_pas_fusionnee updated (an unmatched Odoo line now waits for MERGE_HOLD).
  - main loop: check_health(), check_disk(), check_connections() and check_external_ip() are called at the top of each loop turn. Each one returns at once when not due.
- Bugs fixed: symptom: merge missed when the Odoo line comes first; diagnosis: the nginx and journal sources are read at different speeds; the Odoo line was shown alone (no nginx line held yet); fix: hold the Odoo line too. Symptom: health alert late (21:19 for errors from 14:06, "since 14:06:06"); diagnosis: the periodic checks ran only when the queue was empty or at the end of a line that was not discarded; with --min (default), a busy stream of discarded lines never reached them; fix: checks at the top of each loop turn.
- Safeguards and edge cases: only --log-merge changes behaviour for Odoo lines (the Odoo line is shown later, at most MERGE_WINDOW in log time, or MERGE_HOLD in wall-clock time when no nginx line comes, e.g. a request that did not pass through nginx). The merged line takes the Odoo times and time as before. The checks keep their own timers (no extra alert).
- Checks performed: py_compile; --version; merge check with the Odoo line first and with the nginx line first (both give one merged line with the SQL and time columns); test_i18n (32 tests OK); test_app_log_live: 218 tests, 2 failures, both already present before 1.135 (test_colonnes_jamais_tassees..., test_120_journal_html...); the merge test test_requete_differente_pas_fusionnee updated (the Odoo line now waits too).
- Action required: none. Restart app-log-live.py to load the new version. The [BOT] label of a 403 is already in the column before the OS (since 1.134) for refused robots; a 403 from another user agent has no label.

### 1.134.20261031.212623 - --hide-user-agent; [BOT] in the transfer-time column; traffic light for the transfer time; MAC and OTH; RLQ without www

- Title: the User-Agent text can be hidden (--hide-user-agent); a 403 for a refused robot shows [BOT] in the column before the OS instead of at the end of the line; the transfer time is green under 1 s, yellow from 1 s to 3 s, red from 3 s; the OS column shows MAC (macOS) and OTH (other systems); "rencontres-linux.quebec" without www is shown as RLQ (host=RLQ).
- Reason: 1) the User-Agent text is long and hides the rest of the line. 2) [BOT] at the end of the line is hard to see; the column before the OS is the place of the time. 3) a slow transfer must stand out at a glance. 4) macOS and other systems have no code; the domain without www was not replaced.
- Changes:
  - --hide-user-agent (new option, configuration key HIDE_USER_AGENT): Formatting(hide_user_agent=...) leaves the quoted User-Agent out of the nginx line; the OS column is still computed from it. The existing option --no-user-agent is NOT changed: it stops the reading of the User-Agent (robot detection), which is another thing. Help text and French catalogue updated.
  - aligned_nginx_request(): a 403 answered to a robot of the bot_blocker.conf list (User-Agent read from the line) shows [BOT] in the transfer-time column; the [BOT] label at the end of the line (compose(), since 1.130) is removed.
  - transfer_style(total) and the STYLES keys transfer_ok (green), transfer_mid (yellow), transfer_slow (red): used for the time columns of nginx lines (--log-merge) and of the Odoo requests (werkzeug). Replaces the --slow colour of these columns; --slow keeps its other uses.
  - nginx-tools-tests/test_app_log_live.py: colour expectation of the slow Odoo time (5.5 s is now red, traffic light).
  - os_code(): MAC (Macintosh, Mac OS X; iPhone UAs stay IOS), OTH for any other User-Agent, blanks without User-Agent or with "-".
  - RLQ_DOMAIN_RE: matches the domain with or without the leading dot: "www.rencontres-linux.quebec" shows ".RLQ" (as before), "rencontres-linux.quebec" shows "RLQ".
- Bugs fixed: symptom: host=rencontres-linux.quebec was not replaced (the pattern required a dot before the name); diagnosis: RLQ_DOMAIN_SUFFIX starts with a dot; fix: the dot is optional in the pattern.
- Safeguards and edge cases: --hide-user-agent removes only the User-Agent field with its quotes; the referer and the host stay. A nginx line without the quoted User-Agent is displayed as before. The transfer time of nginx lines is shown only in --log-merge mode: the nginx access format has no request time ($request_time is not logged), so a plain nginx line has no time to colour.
- Checks performed: py_compile; rendering of sample lines (Windows, macOS, SemrushBot 403, python-requests; with and without --hide-user-agent); test_i18n (32 tests OK); test_app_log_live: 186 tests, 2 failures, both already present before 1.134 (test_colonnes_jamais_tassees..., test_120_journal_html...); test_logs_merge OK.
- Action required: none for the program. To see the transfer time on nginx lines outside --log-merge, $request_time would have to be added to the nginx log format (nginx/conf.d/odoo-global.conf) and the program would have to read it: not done.
### 1.133.20261031.205650 - OS column (AND, IOS, WIN, LIN) before the GET; every URL of the line decoded

- Title: each nginx request line shows the system of the client in 3 characters before the GET (AND, IOS, WIN, LIN); all the URLs of the line (requested page and referer) are shown decoded.
- Reason: the referers were shown with their percent codes (%5B, %2C, %2B), hard to read; the operating system of the visitor helps to see which phones or computers request the pages.
- Changes:
  - OS_CODES and os_code(agent): AND (Android, tested before Linux), IOS (iPhone, iPad, iPod), WIN (Windows), LIN (Linux); three blanks when unknown.
  - NGINX_AGENT_RE: takes the User-Agent after the referer of an nginx line.
  - aligned_nginx_request(): the OS column is placed between the numbers and the GET.
  - aligned_request() (Odoo werkzeug lines): three blanks in the same column, so the GET stays aligned.
  - URL_IN_TEXT_RE and Formatting.spans(): every URL of the line has its path and query decoded with display_url(); the host is kept (so the .RLQ tag still applies). Suspicious URLs keep their codes, as for the requested page.
  - nginx-tools-tests/test_app_log_live.py: expected layout of the request columns (4 more blanks before the GET).
  - NUMBERS_BLOCK_WIDTH: 36 to 40 (4 characters for the OS column), so the texts of the Odoo messages stay aligned with the GET.
- Bugs fixed: symptom: referer "%5B8%2C%2B4...%5D" hard to read; diagnosis: only the requested page was decoded (1.128), not the referer; fix: decode every URL of the line.
- Safeguards and edge cases: display_url() still keeps the URL as sent when the decoding gives a control character or a quote (%0A, %22). Mac and other systems show blanks (no MAC code requested). Odoo lines have no User-Agent, so they show blanks in the OS column.
- Checks performed: py_compile; rendering of sample lines (Windows, iPhone, Android, Linux, Mac; %5B, %2C, %20 decoded); test_app_log_live: 177 tests, 2 failures, both already present before 1.133 (test_colonnes_jamais_tassees..., test_120_journal_html...); test_logs_merge and test_i18n OK.
- Action required: none. Restart app-log-live.py to load the new version. The lines are 4 characters longer before the GET.

### 1.132.20261031.202634 - [BOT] follows the bot policy read from bot_blocker.conf (SemrushBot and all refused robots)

- Title: the robots refused by nginx/conf.d/bot_blocker.conf (SemrushBot, AhrefsBot, and the full list) get the [BOT] label and the "bots refused (403)" counter, not only the AI crawlers.
- Reason: a 403 for SemrushBot showed no [BOT] label and lowered the health percentage. Version 1.131 only listed the AI crawlers, while the site policy refuses many more user agents.
- Changes:
  - BOT_BLOCKED_CONF (/etc/nginx/conf.d/bot_blocker.conf) and bot_blocked_re(): the user agent names are read from the "~*(A|B) 1;" lines of the policy file at start-up, so the label follows later changes of the policy.
  - BOT_BLOCKED_DEFAULT: built-in list (same names as the policy at version 1.132), used when the file cannot be read.
  - Comments only elsewhere: is_bot_403() and the BOT_BLOCKED_UA_RE definition.
  - No new user-visible text: lang/app-log-live.fr.po unchanged.
- Bugs fixed: symptom: SemrushBot 403 without [BOT]; diagnosis: BOT_BLOCKED_UA_RE contained only Bytespider, CCBot, GPTBot, Amazonbot, ClaudeBot and Claude-SearchBot, while bot_blocker.conf also refuses AhrefsBot, MJ12bot, SemrushBot, DotBot, DataForSeoBot, PetalBot, SERankingBacklinksBot, GeedoShopProductFinder, and the scanners; fix: take the list from the policy file.
- Safeguards and edge cases: a missing or unreadable policy file falls back to the built-in list; comment lines in the policy file are ignored; names are escaped with re.escape(), so "Palo Alto Networks" (escaped in the policy) matches literally; the match is case-insensitive as in nginx "~*".
- Checks performed: py_compile; loaded the module and checked that the policy file yields the expected names; SemrushBot 403 line recognized; fallback list tested with a missing file.
- Action required: none. Restart app-log-live.py to load the new version.

### 1.131.20261031.200112 - --log-merge shows the Odoo time; automatic status bar at two thirds of the terminal

- Title: with --log-merge, a merged line shows the time of the Odoo line (with hundredths); the automatic status bar appears after two thirds of the terminal height.
- Reason: 1) the nginx time has only seconds (.00), while the Odoo line of the same request has hundredths: the merged line should show the Odoo time. 2) the status bar every (terminal height minus 2) lines was too rare: two thirds of the height is wanted.
- Changes:
  - merge_step(): when an Odoo line is absorbed by its nginx line, the merged line takes the time of the Odoo line (ts_txt).
  - Automatic --status-every: max(5, terminal_rows() * 2 // 3) instead of terminal_rows() - 2. Help text, comment and French catalogue updated.
- Bugs fixed: symptom: no hundredths on the merged lines; diagnosis: the merged line keeps the nginx time; fix: take the Odoo time.
- Safeguards and edge cases: only the displayed time changes; the timing logic (L.instant) is unchanged. Minimum of 5 lines kept for very small terminals. --status-every N still overrides the automatic value.
- Checks performed: py_compile, --version, test_i18n, test_logs_merge (41 tests OK).
- Action required: none. Restart app-log-live.py to load the new version.

### 1.130.20261031.194927 - Robots refused by policy: [BOT] label and own counter, not counted in health

- Title: the 403 answered to the crawlers refused by nginx/conf.d/bot_blocker.conf (Amazonbot, ClaudeBot, GPTBot, CCBot, Bytespider, Claude-SearchBot) are shown with [BOT] at the end of the line, counted apart as "bots refused (403)", and no longer lower the health percentage.
- Reason: a 403 for Amazonbot and ClaudeBot was shown without explanation, and it counted as an error in the health percentage, although it is the expected result of the site policy.
- Changes:
  - BOT_BLOCKED_UA_RE (same list as bot_blocker.conf), REQUEST_CODE_RE and is_bot_403(L): recognizes an nginx request answered 403 to one of these User-Agents.
  - compose(): adds the [BOT] label (style "debug") at the end of such lines.
  - Stats.observe(): these 403 go to self.bots403 instead of e4 and codes; they do not make the address a "problem" address.
  - Stats.pieces(): line "bots refused (403): N", only when N is not zero.
  - Stats.health(): unchanged formula, the bot 403 take no points (docstring updated).
  - lang/app-log-live.fr.po: entries for the new messages.
- Bugs fixed:
  - Symptom: 403 lines for the bots with no label, and a lower health percentage.
  - Diagnosis: every 4xx counted in e4, and e4 weighs 0.1 point each in the health percentage.
  - Fix: the 403 of the bot policy are counted apart.
- Safeguards and edge cases:
  - Only nginx lines (database "nginx") and only the 403 code: a 403 from another reason or a 403 to a normal browser is still counted as an error.
  - The list must follow bot_blocker.conf: if a bot is added there, add it to BOT_BLOCKED_UA_RE too (see comments).
  - The UA is searched in the whole line: a URL containing one of these names would be matched as well (very rare).
- Checks performed: py_compile, --version; is_bot_403 on the two lines of the report (True), on a 403 to a browser (False), on a 200 to ClaudeBot (False), on an Odoo line (False); test_i18n OK; test_app_log_live and test_logs_merge: 186 tests, the 2 failures are the ones already present before this change (test_colonnes_jamais_tassees..., test_120_journal_html_un_fichier_par_jour).
- Action required: none. The new behaviour applies at the next start of app-log-live.py.

### 1.129.20261031.172912 - Browser version numbers are no longer taken for IP addresses

- Title: in the User-Agent, the version after the browser name (Chrome/146.0.0.0) is shown as it is, and is no longer replaced by the owner and the country of an address.
- Reason: the user saw, after "Chrome/", a name of an organisation and a country (for example "Chrome/RIPE Network Coordination Centre (org) [NL 146.0.0.0]") instead of the version: the version was read as an IP address.
- Changes:
  - app-log-live.py, IPV4_RE: an address preceded by a single "/" is no longer an address (lookbehind (?<![^/]/)). "//" stays allowed, so https://1.2.3.4/ is still found.
  - nginx-tools-tests/test_app_log_live.py: test_version_du_navigateur_n_est_pas_une_adresse (Chrome/146.0.0.0 is not an address; addresses in URLs and in the text are still found).
  - Files touched: app-log-live.py, CHANGELOG.md, nginx-tools-tests/test_app_log_live.py.
- Bugs fixed:
  - Symptom: "Chrome/" followed by an organisation name and a country code, in the User-Agent of nginx lines.
  - Diagnosis: the version 146.0.0.0 matches the IPv4 pattern; the program then renders it as an address (owner of its block, country) in place of the text.
  - Fix: the address is not detected when it follows a single "/".
- Safeguards and edge cases:
  - A real address written after a single "/" in a path (for example /whitelist/1.2.3.4) is no longer replaced by its name. Such paths are rare; say if it matters.
  - IPv6 detection is unchanged.
  - The address of the client in the column is unchanged (it is not after a "/").
- Checks performed:
  - python3 -m py_compile on app-log-live.py and the test file.
  - find_ips on the User-Agent of the attached log (no address found), on https://1.2.3.4/ and on plain text (addresses found).
  - Test modules test_app_log_live and the others, with the testeur agent.
- Action required: none.

### 1.128.20261031.141237 - Domain shown as ".RLQ" in the text of the lines, URLs shown decoded

- Title: in the text of the lines, ".rencontres-linux.quebec" is shown as ".RLQ" in colour (referer and host=...); a URL written with %XX codes is shown decoded (%20 becomes a space).
- Reason: the user saw that the domain was only changed in the name column; the text of the line (referer, host=) still had the full domain. The user also asked to show the real URL instead of the encoded form of /web/image/... (the percent codes).
- Changes:
  - app-log-live.py, detection of the highlighting (function that colours the text of a line): RLQ_DOMAIN_RE and RLQ_TEXT_TAG (".RLQ"); every occurrence of the domain in the text gets the place colour.
  - app-log-live.py, display_url(): the URL decoded with unquote() when it contains "%". It is NOT decoded when the result has a control character or a quote (%0A, %22...: the line would be broken). Used by the colours of the 5xx and 4xx URLs and by a URL with "%" and no other colour. A suspect URL (suspect_url) keeps its raw form (%2e%2e stays visible). The raw URL is still used for the checks.
  - nginx-tools-tests/test_app_log_live.py: test_texte_de_la_ligne_domaine_RLQ_et_url_decodee.
  - Files touched: app-log-live.py, CHANGELOG.md, nginx-tools-tests/test_app_log_live.py.
- Bugs fixed: the domain stayed in full in the text of the lines (see 1.127, which changed only the names). Symptom: "odoo-dev.rencontres-linux.quebec" in the referer and host=. Diagnosis: the name tag was applied only in render(). Fix: a detection on the text.
- Safeguards and edge cases:
  - The tag in the text is ".RLQ" (as asked), while the names keep ".RLQ." (1.127). The two forms are kept apart on purpose; say if both must be the same.
  - The match needs the leading dot: a bare "rencontres-linux.quebec" is not changed.
  - The decoded URL can contain spaces: the display is only a view, the columns of the line are computed before the decoding.
  - Detection is case-insensitive for the domain only; the URL is decoded with unquote (the + sign stays a plus).
  - Two tests of the earlier version failed (suspect URL with %2e%2e, URL with %0A and %3D"): fixed by the rules above.
- Checks performed:
  - python3 -m py_compile on app-log-live.py and the test file.
  - Manual reproduction of the line of the request (nginx form) with the parser and the formatter: referer and host= show ".RLQ", the URL is decoded.
  - Test modules test_app_log_live and the others, with the testeur agent.
- Action required: none.

### 1.127.20261031.133408 - Domain name shown as ".RLQ." (colour) in the names

- Title: in the names of the lines, the domain ".rencontres-linux.quebec" is shown as ".RLQ." in colour, to save room on the line (for example "odoo18.RLQ." instead of "odoo18.rencontres-linux.quebec").
- Reason: the user asked to save space on the display; the long domain takes many characters of each name.
- Changes:
  - app-log-live.py, render(): a name that ends with ".rencontres-linux.quebec" (case ignored) is shown with ".RLQ." instead, the tag in the colour of the places (STYLES["place"]); the cut of --dns-max-truncate is applied on the shorter text. Constants RLQ_DOMAIN_SUFFIX and RLQ_TAG.
  - app-log-live.py, consumer: state "consumed" (set when a line is really processed), used by the startup bar (see 1.126).
  - nginx-tools-tests/test_app_log_live.py: test_nom_du_domaine_rlq_affiche_en_tag_RLQ (the tag is in colour; other names are unchanged).
  - Files touched: app-log-live.py, CHANGELOG.md, nginx-tools-tests/test_app_log_live.py.
- Bugs fixed: none in this version (the startup bar fix is described in 1.126).
- Safeguards and edge cases:
  - The bare domain "rencontres-linux.quebec" (without a subdomain) is not changed: the match needs the leading dot.
  - Only the names are changed; the text of the Odoo messages and the addresses are not.
  - Without colour (output redirected) the tag stays ".RLQ.".
- Checks performed:
  - python3 -m py_compile on app-log-live.py and the test file.
  - Test modules test_app_log_live and the others, with the testeur agent.
- Action required: none.

### 1.126.20261031.132627 - Status bar at startup: after all the history lines, with date and host

- Title: the status bar shown at startup comes after ALL the history lines, and its first display carries the date and the host name (with --status-header).
- Reason: the user saw the first status bar before the last history lines, and without the date and the server name; the following bars were correct.
- Changes:
  - app-log-live.py, startup_status_bar(): new function, called from the idle branch of the consumer (queue empty for one second) and at the end of the stream. The bar is written once, when at least one line was read, and no line is held by --log-merge.
  - show_summary(): the bar is no longer written there (it was written when the N-th line was counted, before the last history lines).
  - Files touched: app-log-live.py, CHANGELOG.md, nginx-tools-tests/test_app_log_live.py.
- Bugs fixed:
  - Symptom: the bar appeared in the middle of the history, before the last lines. Diagnosis: the bar was written when read_files (lines counted after the filters) reached --lines; the lines after it (deferred failed requests, lines held by --log-merge) were printed later. Fix: the bar waits for the queue to be empty.
  - Symptom: the first bar had no date and no host with --status-header. Diagnosis: the reader counts a line BEFORE queuing it, so the idle test "a line was read" was true while the queue was still empty: the bar was written before any history line had set the stamp. Fix: the test uses the lines really processed by the consumer (state "consumed"), so the stamp of the last displayed line is known.
- Safeguards and edge cases:
  - A history shorter than --lines (the journal has fewer lines) also gets its bar: the first idle moment ends the history.
  - A history line held by --log-merge or deferred (failed request) delays the bar until it is displayed.
  - --status-every 0 still means never.
  - With --no-follow, the bar is written at the end of the stream, before the session summary.
- Checks performed:
  - python3 -m py_compile on app-log-live.py and the test file.
  - Test test_bout_en_bout_bar_de_statut_apres_l_historique: the bar comes after the last history line and carries the date and the host with --status-header.
  - Test modules test_app_log_live and the others, with the testeur agent.
- Action required: none.

### 1.125.20261031.124344 - --config-merge, status bar figures in colour, time on the lines with --status-header, status bar at startup

- Title: new option --config-merge (rewrites the configuration file from the new default configuration, keeping the values already set); with --status-header the time stays on each line and the date (without time) and the host name go to the status bar; each figure of the status bar has its own colour (green, yellow, red) according to its criticality; the status bar is shown once after the history at startup.
- Reason: the user asked for a --config-merge option to use the new default configuration while keeping the values changed in the current configuration; asked that, with STATUS_HEADER, only the date (not the time) and the server name are in the status bar, and the time is back on the lines; asked that the digits of the status bar change colour from green to red according to their criticality; and asked that the status bar be displayed at startup, after the history.
- Changes:
  - app-log-live.py, --config-merge (new option, alphabetical place after -c/--config): config_merge() reads the configuration files that the program reads (the given one with -c, otherwise /etc/default/app-log-live.conf and then ~/.app-log-live.conf, the last one wins), takes the keys set (uncommented) in them, and rewrites the file (the last one read, or the personal file when none exists) from doc/fr or doc/en/app-log-live.conf.example (language of the program). The keys unknown to the program are listed and left out. The program then exits.
  - app-log-live.py, apply_values() (lines of a configuration file with the values applied) and write_lines() (temporary file then replacement, rights kept): factored out of write_config(), which keeps its behaviour.
  - Formatting.format_value(): with --status-header (STATUS_HEADER), the time of the line is shown (ts_txt without the date); the host name is no longer on the line.
  - emit(): the stamp of the status bar is the date and the host name of the last line (the time is no longer in the bar).
  - StatusBar.pieces(): the bar as (text, colour) pieces; criticite(value, yellow, red) gives 32, 33 or 31. Thresholds: SQL injection 1 and 5; 4xx 20 and 100 (total and by code); 5xx 1 and 5 (total and by code); banned addresses 1 and 5; slow requests 5 and 20; max SQL 300 and 1000; Odoo errors 1 and 10; health 90 and 70 (green from 90, yellow from 70, red below). summary() is the text of pieces(), unchanged for the other callers. codes_pieces() replaces codes_text() in the pieces (codes_text() keeps its text).
  - status_line(): each coloured piece is drawn with its own colour (reverse video, as the bar), then the bar colour again; the cut at the width of the terminal counts the visible characters only (the escape sequences are not counted).
  - Startup: the status bar is written once when the history has been displayed (end of the history, before the live lines), unless --status-every is 0 (never).
  - --status-header help text (msgid and msgstr in lang/app-log-live.fr.po) and new msgids for --config-merge and its messages (French translation added).
  - doc/en/07-app-log-live.md and doc/fr/07-app-log-live.md: --config-merge, STATUS_HEADER behaviour, figures in colour, status bar at startup.
  - doc/en/app-log-live.conf.example and doc/fr/app-log-live.conf.example: comment above #STATUS_HEADER=no.
  - nginx-tools-tests/test_app_log_live.py: the two STATUS_HEADER tests are updated (time on the line, date and host in the bar); new tests: criticite(), coloured pieces, --config-merge (values kept, unknown key reported, backup), status bar at startup. The debugging print of an earlier test is removed.
  - Files touched: app-log-live.py, CHANGELOG.md, lang/app-log-live.fr.po, doc/en/07-app-log-live.md, doc/fr/07-app-log-live.md, doc/en/app-log-live.conf.example, doc/fr/app-log-live.conf.example, nginx-tools-tests/test_app_log_live.py.
- Bugs fixed: the French help of --log-merge, --status-header and --config-merge mixed French and English words (for example "depuis the NEW default"): the msgids were missing from lang/app-log-live.fr.po. Symptom: a translator substitutes word by word when the msgid is missing. Diagnosis: the catalogue had no entry for these texts. Fix: the entries were added.
- Safeguards and edge cases:
  - --config-merge never writes without a backup when the file exists: FILE.bak-YYYYMMDD-HHMMSS (local time) is a copy made before the rewrite.
  - A file that cannot be written (rights, /etc/default without root) is reported, with exit status 1; the backup is then kept.
  - A missing example file is reported (exit status 1) and nothing is written.
  - Keys of the old file that are neither known to the program nor in the example are left out and listed, never silently lost in the message.
  - A value that contains "#" or spaces at the edges is written between quotes, as before.
  - Colours are disabled when the output is redirected: the figures are plain text then (the text is identical).
  - Startup status bar: only when the history has been displayed and --status-every is not 0; with --no-history (no history) there is no bar until the first periodic one.
- Checks performed:
  - python3 -m py_compile on app-log-live.py and the test file.
  - Manual run: python3 app-log-live.py -c FILE --config-merge on a temporary file (values kept, unknown key listed, backup created).
  - Unit and end-to-end tests of class AppLogLive123 (test_app_log_live.py), with the testeur agent.
- Action required: to keep the configuration file up to date, run once: app-log-live.py --config-merge (add -c FILE for a particular file). Otherwise none.

### 1.124.20261031.115734 - 4xx and 5xx by code in the status bar, configuration keys for --log-merge and --status-header

- Title: the status bar shows the 4xx and the 5xx answers by code (for example "4xx 3 (403: 1 - 404: 2)" and "5xx 1 (500: 1)"); the options --log-merge and --status-header can be set in the configuration file (keys LOG_MERGE and STATUS_HEADER).
- Reason: the user asked to see the 403 and 404 answers separately in the status bar, and the same for the 5xx answers; and asked that each option added on the command line has a key in the configuration file (LOG_MERGE for --log-merge, STATUS_HEADER for --status-header).
- Changes:
  - StatusBar.codes (Counter): observe() counts each 4xx and 5xx answer by its code, next to the existing totals e4 and e5 (which are unchanged: the health and the colours do not change).
  - StatusBar.codes_text(first, total): "4xx 172 (403: 3 - 404: 169)"; without any answer of the class, the total alone ("4xx 0"). summary() uses it for 4xx and 5xx.
  - SCHEMA_CONFIG: "LOG_MERGE" -> log_merge and "STATUS_HEADER" -> status_header (boolean keys, as LOG_NGINX). The value of the file becomes the default of the option; the command line still has priority.
  - Help of --config: the list of the keys in UPPERCASE now includes LOG_MERGE and STATUS_HEADER (lang/app-log-live.fr.po updated, msgid and msgstr).
  - doc/en/app-log-live.conf.example and doc/fr/app-log-live.conf.example: #LOG_MERGE=no and #STATUS_HEADER=no.
  - doc/en/07-app-log-live.md and doc/fr/07-app-log-live.md: configuration keys and the split of the 4xx and 5xx answers.
  - nginx-tools-tests/test_app_log_live.py: new tests in class AppLogLive123 (status split by code, the two keys in SCHEMA_CONFIG, end-to-end reading of LOG_NGINX, LOG_MERGE and STATUS_HEADER from a file given with -c).
  - Files touched: app-log-live.py, CHANGELOG.md, lang/app-log-live.fr.po, doc/en/app-log-live.conf.example, doc/fr/app-log-live.conf.example, doc/en/07-app-log-live.md, doc/fr/07-app-log-live.md, nginx-tools-tests/test_app_log_live.py.
- Bugs fixed: none.
- Safeguards and edge cases:
  - A code outside 400-599 is never counted here (only the 4xx and 5xx answers reach codes).
  - With many different codes, the status bar is longer: it is still cut at the width of the terminal, as before.
  - The two new keys are booleans: LOG_MERGE=yes works only with LOG_NGINX=yes (see the option help).
  - The status bar counters are still reset by Ctrl-T and g, with the codes.
- Checks performed:
  - python3 -m py_compile; the unit and end-to-end tests of class AppLogLive123 (10 tests, all pass).
  - Earlier failures of the full suite that already existed before the change: test_colonnes_jamais_tassees_pays_noms_anonymises_et_souligne_tous_les_n and test_120_journal_html_un_fichier_par_jour (not touched).
- Action required: none. To use the keys: add LOG_MERGE=yes and STATUS_HEADER=yes in /etc/default/app-log-live.conf or in ~/.app-log-live.conf.

### 1.123.20261031.105019 - Shorter lines (ERR, WARN, H1.1, "..."), --status-header, --log-merge

- Title: the lines are shorter: the level is written in 4 characters (ERR, WARN, CRIT, DBUG, INFO), the HTTP protocol as H1.1, and the marker of a shortened line is the single character "..." instead of "...". Two new options: --status-header (date and host name moved from each line to the start of the status bar) and --log-merge (the nginx line and the Odoo line of the same request become ONE line).
- Reason: the user asked to save characters on each line (level column limited to 4 characters, "H1.1" instead of "HTTP/1.1", "..." instead of "..."), to remove the date and the server name from each line when they are already shown elsewhere, and to combine the nginx line and the Odoo line of one request (the name --log-merge was proposed by the user).
- Changes:
  - LEVEL_WIDTH 8 -> 4 and LEVEL_SHORT (CRITICAL -> CRIT, DEBUG -> DBUG, ERROR -> ERR, WARNING -> WARN). format_value() writes the short level; the colours are unchanged.
  - short_http() ("HTTP/1.1" -> "H1.1"), used by aligned_request() (Odoo lines) and aligned_nginx_request() (nginx lines). NUMBERS_BLOCK_WIDTH 40 -> 36 so that the requests keep their column.
  - ELLIPSIS = "..." (one character): shorten_line() (--truncate, default on a terminal), the help texts of --truncate and the messages of the screen (lang/app-log-live.fr.po updated: msgid and msgstr). The names cut by --dns-max-truncate already used "...".
  - --status-header: format_value() writes only the program name (no date, no host name) when set; the status bar starts with the date and the host name of the last displayed line (state["stamp"], set by emit()). Formatting takes the new argument status_header.
  - --log-merge: merge_step() and merge_release() (module level) and the consumer loop of main(): an nginx request line is held up to MERGE_HOLD (3 seconds, wall clock) waiting for the Odoo line with the same method and URL and the same status, whose log time is within MERGE_WINDOW (2 seconds). When found, the Odoo line is absorbed and its SQL queries and times are stored on the nginx line (Line.odoo_times): aligned_nginx_request() shows them in the empty columns of the nginx line, and the slowness colour uses them. An nginx line without its Odoo line is shown alone after 3 seconds, at the end of the stream, or when the next line is more than 2 seconds later. --log-merge only works with --log-nginx (both are needed to see the two lines).
  - Options added in the help (sorted alphabetically with the others, in colour): --log-merge, --status-header.
  - doc/en/07-app-log-live.md and doc/fr/07-app-log-live.md: the two options and the display changes.
  - lang/app-log-live.fr.po: texts of the two new options, and the "..." texts.
  - nginx-tools-tests/test_app_log_live.py: expected texts updated (H1.1, ERR, WARN, "...", column positions shifted by 4 characters); new class AppLogLive123 (5 unit tests and 2 end-to-end tests: one line per request with --log-merge, status bar with --status-header).
  - nginx-tools-tests/test_logs_merge.py: column positions of the nginx and Odoo lines shifted by 4 characters (level on 4 characters).
  - Files touched: app-log-live.py, CHANGELOG.md, lang/app-log-live.fr.po, doc/en/07-app-log-live.md, doc/fr/07-app-log-live.md, nginx-tools-tests/test_app_log_live.py, nginx-tools-tests/test_logs_merge.py.
- Bugs fixed: none in this version. Note: a merged line keeps the name, address and country of the nginx line; the Odoo line is not displayed on its own (its numbers are in the merged line). Its errors, if any, are separate log lines and are still shown.
- Safeguards and edge cases:
  - Without --log-nginx, --log-merge does nothing (the nginx lines are then hidden: merging them would hide the requests).
  - The key x (show or hide the nginx lines) turns the merge on and off with the option: the merge only runs while the nginx lines are shown.
  - A request without SQL numbers (websocket, longpolling) is not merged.
  - An nginx line whose Odoo line is missing (static file, request served by nginx alone) is shown as before, alone, after 3 seconds.
  - Lines are shown in the order of their arrival; a merged line appears at the position of its Odoo line, so a line may come out up to 2 seconds late compared to the lines that were not held.
  - The filters (--only, --grep, --since, --country) apply to the merged line, as they do to each line.
  - At the end of the stream (--no-follow), every held line is shown.
  - Level names of the logs are unchanged: only the display uses the short names (the summary keeps "ERROR / CRITICAL").
- Checks performed:
  - python3 -m py_compile; ruff: same 60 findings as before the change (no new finding).
  - Unit tests: test_app_log_live (all modules, 246 tests run, the failures listed below are expected texts that were updated), test_logs_merge, test_alignement, test_i18n, test_conventions, test_docs. Before the change: 3 failures already present (test_changelog_plus_recent_en_premier for web-monitor.py and odoo-warmup.py, test_colonnes_jamais_tassees_pays_noms_anonymises_et_souligne_tous_les_n) and test_120_journal_html_un_fichier_par_jour (also failing before the change, not touched).
  - New tests: AppLogLive123 (7 tests, all pass).
  - Manual check on lines in the real journal format (nginx "http:" and Odoo "werkzeug" lines): 6 lines gave 4 lines with --log-merge; the H1.1 block carries the SQL and time numbers of Odoo.
  - Not verified here: the display on a real Odoo and nginx server (the logs of the server were not available in this session), and the screen rendering with --status-header in a terminal.
- Action required: none. New options if wanted: --log-merge (with --log-nginx) and --status-header.

### 1.122.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: the detail command of the Ctrl-C summary was shown as "--erreurs-only" instead of "--errors-only": the French catalogue key "errors" (made from "error(s)") was also replaced inside the option name. Diagnosis: test_ctrl_c_demande_confirmation_puis_detail_des_erreurs failed. Fix: the translator of apps/_i18n.py no longer replaces a word right after "--" (see the entry of apps/_i18n.py).
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

### 1.121.20261030.143010 - Status bar on g and Ctrl-C, no quotes in requests, sizes in 4 characters, requests per port

- Title: the status bar is shown when the user presses g (or Ctrl-G) and before the Ctrl-C question; the size column takes at most 4 characters (9999, then 2.9k, 600k, 4.5M); the quotes around the requests are removed; the status bar counts the requests per port (nginx server port and Odoo upstream port).
- Reason: the user asked for the status bar on Ctrl-C and g; for the quotes to be removed from the text (they were still shown on the Odoo lines, and the nginx lines still had some); for the byte column to take less room (4 characters, with k and M above 9999 bytes); and for the number of transactions per port 443 and per Odoo port (10000, 10002).
- Changes:
  - key g (and Ctrl-T): the status bar line is written before its counters are reset, so the period just reported is seen.
  - confirm_exit (Ctrl-C): the status bar line is written before the "Quit ?" question.
  - size_text(): values up to 9999 are written as they are; above, decimal units: 2.9k, 600k, 4.5M (1 k = 1 000 bytes). SIZE_WIDTH = 4 (was 7), NUMBERS_BLOCK_WIDTH = 40 (was 42): the request of Odoo and nginx lines keeps its column.
  - aligned_request (Odoo lines): the request is written without its quotes, with three spaces before it, as the nginx lines.
  - PORT_RE (port=NNN) and UPSTREAM_PORT_RE (upstream=HOST:PORT) read on the nginx access lines; StatusBar.ports counts each request for the ports it carries; the summary shows "per port: 443: 12, 10000: 3" or "per port: no port data" when the log format does not give the port.
  - lang/app-log-live.fr.po: "per port" and "no port data".
  - nginx-tools-tests/test_app_log_live.py: expected lines updated (no quotes, 4-character size column, 3 spaces before the request, the helper block()); the wait before the answer to the Quit question is 1 second (was 0.2).
  - Files touched: app-log-live.py, lang/app-log-live.fr.po, nginx-tools-tests/test_app_log_live.py, CHANGELOG.md.
- Bugs fixed:
  - Symptom: the answer to the "Quit ?" question sent after 0.2 s was read by the keyboard handler (menu --only) and the program did not quit. Diagnosis: the status bar written just before the question delays the start of the question; the keys thread still reads the keyboard. Fix: the test waits 1 s; a person does not answer this fast, the program is unchanged in that respect.
- Garde-fous and edge cases:
  - Sizes: "-" (Odoo) and any value that is not a number are written as they are.
  - Ports: without port= and upstream= in the log, nothing is counted and the bar says so; no port is invented.
  - The raw access-log lines of BigBlueButton (not in the combined_host form) keep their quotes: they do not go through the aligned form. To be handled separately.
- Not in this version (decisions needed):
  - Per-port counts need two variables in the nginx log format: port=$server_port and upstream=$upstream_addr. This is a change to the nginx configuration of each server, not made here (test_config_nginx checks the format). Action required: add them to combined_host, then tell the program with the next run.
  - Odoo mail task: design written in the project (claude/design-odoo-mail-task.md), to be validated.
  - Plural markers, setup percentage, HTML report every N hours, Odoo spreadsheet export: see 1.120.
- Checks:
  - size_text(): 0, 9999, 10000 (10k), 600000 (600k), 999600 (1.0M), 4500000 (4.5M).
  - Full unit test run (958 tests): 8 failures, all already present on the base commit (terminal width of test_colonnes_jamais_tassees, odoo-backup model order, the configuration model tests, odoo-warmup CHANGELOG order, menu key log_nginx). No new failure.
- Action required: add port=$server_port and upstream=$upstream_addr to the log_format combined_host of the nginx sites to see the requests per port; without them the bar shows "no port data".

### 1.120.20261030.104109 - Status bar every N lines (automatic), health percentage, more counters, HTML daily journal

- Title: the status bar is shown every N displayed lines, N chosen from the height of the terminal by default; the bar shows a health percentage out of 100, and new counters: most SQL queries of one request, Odoo errors, Odoo users signed in and SSH sessions; the displayed journal is also saved every day as an HTML page, lines cut at 140 characters.
- Reason: the user asked for a status bar that is shown regularly whatever the terminal size, a health percentage that falls with attacks and is reset with Ctrl-T, more counters (maximum transactions, banned addresses, Odoo users, SSH, Odoo errors), and a copy of the display in HTML, one file per day, with lines cut at 140 characters.
- Changes:
  - --status-every: the default is now -1 = automatic, which means the terminal height minus 2 lines (at least 5). 0 still means never; any other number is taken as it is. Validation accepts -1 and above.
  - terminal_rows(): height of the terminal ($LINES, then the terminal itself), 24 when unknown, at least 10.
  - StatusBar.health(): 100 minus 3 points per SQL injection attempt, 2 per 5xx, 0.1 per 4xx, 2 per banned address and 1 per slow connection; never below 0. Reset by Ctrl-T and g with the other counters.
  - StatusBar.observe: the most SQL queries of one request (group 5 of WERKZEUG_RE) and the Odoo ERROR and CRITICAL lines (nginx errors are not counted).
  - StatusBar.summary(users, ssh): the health, the new counters, and the users and SSH sessions when the caller gives them (status_line() computes them: odoo_logged_in() and ssh_sessions()).
  - Output: a copy of the daily journal in HTML, app-log-live-DATE.html in the same folder as the .log file (mode 600, file not followed when it is a link). ansi_to_html() turns the colours and the bold and underline styles into spans, html_line() cuts each line at HTML_LINE_WIDTH = 140 visible characters. The page is closed with its end tags when the day changes and at exit. purge() also removes the old HTML pages.
  - --no-html-journal: no HTML copy. Not in the configuration file: this option can only be given on the command line for now.
  - lang/app-log-live.fr.po: "lente(s)" becomes "lentes"; new entries for health, max SQL, Odoo errors, Odoo users and SSH.
  - nginx-tools-tests/test_app_log_live.py: class AppLogLive120 (6 tests: HTML cut at 140 characters, escaping and colours, health and reset, new counters, one HTML file per day with its end, automatic interval).
  - Files touched: app-log-live.py, lang/app-log-live.fr.po, nginx-tools-tests/test_app_log_live.py, CHANGELOG.md.
- Bugs fixed:
  - Symptom: the HTML page of the previous day was left without its end tags and its file kept open when the day changed. Diagnosis: _open() started the new page without closing the old one. Fix: close_html() is called first, in _open_html() and in close().
  - Symptom: the French screen showed "app-santé-check.py" and "--santé MIN", and the settings test could not find options["health"]. Diagnosis: the translation replaces each msgid wherever it appears, so the msgid "health" changed the words of other texts. Fix: the msgid is "health state", which appears in no other text.
- Not done in this version (to be decided with the user):
  - The "(s)" plural markers still appear in the other messages of app-log-live.py and in the other programs (about 400 places); a single count-aware helper is proposed for the next step.
  - Setup completion percentage, Odoo task to send e-mail without Postfix, HTML summary report every N hours, and export of statistics to the Odoo spreadsheet module: design needed first.
- Safeguards and edge cases:
  - Automatic status interval: a very small or unknown terminal gives at least 5 lines between two bars, never a division by zero.
  - Health cannot go below 0; a huge number of attacks only gives 0 %.
  - The max SQL count is a maximum since the last reset, not an average.
  - HTML text is escaped; no external resource is loaded by the page.
- Checks:
  - Functional check of the HTML lines (140 characters, colours kept), of the health formula and reset, of the summary text, and of two HTML pages with their end tags.
  - Unit tests: AppLogLive120, 6 tests, all pass.
  - Full run (958 tests): the failures that remain are the same as on the base commit: the terminal width of test_colonnes_jamais_tassees, the configuration model tests (options --buffer, --country and others, BUFFER and STATUS_EVERY missing from the model; --no-html-journal joins them), odoo-backup model order, odoo-warmup.py CHANGELOG order, and the menu key log_nginx.
- Action required: none.

### 1.119.20261030.074937 - Dashboard title, status bar colour from slow connections only, nginx lines without quotes and with [BANNIE]

- Title: the program shows "Tableau de bord en temps réel de APP" (APP = Odoo or BigBlueButton, from APP_LABEL) at startup and with Ctrl-T.
- Reason: the user asked for a title at startup and on the Ctrl-T summary; the status bar changed colour for 4xx, 5xx, SQL injections and banned addresses, but only the slow connections should change it; the top addresses showed "(3)", and the user asked for no parentheses; the nginx lines had double quotes around the request, the referer and the agent; the banned addresses of nginx lines must be shown as [BANNIE] at the end; the truncation marker "..." had spaces around it, which made the URL longer.
- Changes:
  - Title: options["app_label"] (from APP_LABEL) and the line "Real-time dashboard of {app}" (translated in lang/app-log-live.fr.po); printed by main at startup, and before the table of the Ctrl-T key.
  - StatusBar.color: follows ONLY the slow connections, those of more than STATUS_SLOW_S = 9 s (new constant): 1 to 4 green, 5 to 19 yellow, 20 and more red. StatusBar.observe counts them with the same rule. The other problems are still counted and shown in the text of the bar, but do not change its colour.
  - StatusBar.top_ips: "IP ×2" instead of "IP (2)".
  - Formatting.compose: a banned address of an nginx line is labelled [BANNED] (French: [BANNIE]) at the end of the line; Odoo lines keep "[banned: source]".
  - shorten_line: the marker "..." has no space around it ("start...last two words").
  - Formatting.aligned_nginx_request: the request, the referer, the agent and the host of nginx lines are shown without double quotes; the request keeps the column of the Odoo request (three spaces instead of two). Odoo lines keep their quotes.
  - nginx-tools-tests/test_app_log_live.py: expectations updated (colour rules, ×, ...); nginx-tools-tests/test_logs_merge.py: no quotes in an nginx line, GET at the column of the Odoo GET.
  - Files touched: app-log-live.py, lang/app-log-live.fr.po, nginx-tools-tests/test_app_log_live.py, nginx-tools-tests/test_logs_merge.py, CHANGELOG.md.
- Bugs fixed:
  - Symptom: Ctrl-G and Ctrl-T stopped the program (NameError). Diagnosis: the title was built from profile, which the key handler cannot see. Fix: the label is read from options["app_label"].
- Safeguards and edge cases:
  - The "[BANNED]" label is only for nginx lines; Odoo lines keep "[banned: fail2ban]" or "[banned: CrowdSec]".
  - The quotes are removed from nginx lines only; the request of an Odoo line keeps its quotes, so the two kinds of lines stay different.
  - The colour of the status bar no longer depends on --slow for its colour; --slow still colours the lines.
- Checks:
  - Rendering: the GET of the nginx request and of the Odoo request are in the same column; no quote in the nginx line.
  - Full test_app_log_live run: 154 tests, only test_colonnes_jamais_tassees fails (already failing on the base branch because of the terminal width).
- Action required: none.

### 1.118.20261030.000133 - Size column 2 characters wider, f key keeps the underlined lines, nginx words in colour

- Title: the size column holds 7 characters (up to 9 999 999 bytes); the f (refresh) key underlines the same lines as the screen; the nginx program and database words are shown in bold magenta.
- Reason: a size of 1962191 pushed the request of the nginx line out of its column (5 characters were too few); after the f key the lines were displayed without the underline, which made them hard to follow; the nginx lines were hard to tell apart from the Odoo lines.
- Changes:
  - SIZE_WIDTH = 7 (was 5), NUMBERS_BLOCK_WIDTH = 42 (was 40): the request of every Odoo and nginx request line moves 2 columns to the right.
  - refresh_lines (f key): each line of the buffer keeps its emission number ("n"); it is written with the same underline rule as on screen (one line out of N, N = --underline).
  - STYLES["nginx"] = "1;35" (new style): the program word (http) and the database word (nginx) of nginx lines are in bold magenta in the header. The padding of the header is computed on the plain text, so the colour takes no column.
  - nginx-tools-tests/test_app_log_live.py: size expectations updated to 7 characters; new test test_touche_f_redessine_les_lignes_soulignees (f key, underline on the redrawn lines).
  - Files touched: app-log-live.py, nginx-tools-tests/test_app_log_live.py, CHANGELOG.md.
- Bugs fixed:
  - Symptom: after the f key the lines were displayed without underline. Diagnosis: refresh_lines called output.write without the underline argument. Fix: the underline rule is applied again to the redrawn lines.
  - Symptom: a size of 7 digits pushed the request of the nginx line to the right. Diagnosis: the size column was 5 characters wide. Fix: 7 characters.
- Safeguards and edge cases:
  - A size with more than 7 digits (more than 9 MB) still pushes the request one column to the right; not seen on this site.
  - --min, --no-underline and --underline 0: unchanged (no underline is drawn).
  - Colours are added to the program and database words only; the plain text and the columns are unchanged.
- Checks:
  - Rendering with the real Formatting: nginx and Odoo request lines have the country at the same column, the request at the same column, and the size of 1962191 ends at the same column as the Odoo dash.
  - test_touche_f_redessine_les_lignes_soulignees fails on the previous version and passes on this one.
  - Full test_app_log_live run: see the result line of this version (only test_colonnes_jamais_tassees is expected to fail, already failing on the base branch because of the terminal width).
- Action required: none.

### 1.117.20261029.233250 - nginx requests aligned on the status, the size and the request of Odoo lines

- Title: the status code, the size and the request of nginx access lines are in the same columns as those of the Odoo request lines; the level is right-aligned on 8 characters for every line (option A chosen by the user).
- Reason: the user pasted nginx and Odoo lines of the same request: the country and the name were aligned, but the HTTP code, the size and the request were not, and the ERROR and CRITICAL lines shifted the country by 1 and 3 columns. The user asked that everything be aligned, with option A (the level in a fixed 8-character field, which moves the Odoo lines too).
- Changes:
  - Formatting.format_value: the level is right-aligned on 8 characters (LEVEL_WIDTH, new constant): INFO, ERROR and CRITICAL keep the country, the address and the name in the same columns. The width compensation after the address is removed (it was the cause of the shift).
  - NGINX_REQUEST_RE (new regex) and Formatting.aligned_nginx_request (new method): an nginx access line gets the same block as an Odoo request, status and size first, then the request, then the referer, agent and host as text. The SQL and time columns stay empty (nginx does not log them).
  - Formatting.aligned_request: the size column is SIZE_WIDTH (5 characters, new constant) instead of 4, so a size of 10 kB or more does not move the request; NUMBERS_BLOCK_WIDTH is 40 (was 39).
  - nginx-tools-tests/test_logs_merge.py: the alignment test also checks the HTTP code, the request and the end of the size against the Odoo line.
  - Files touched: app-log-live.py, nginx-tools-tests/test_logs_merge.py, CHANGELOG.md.
- Bugs fixed:
  - Symptom: "HTTP/1.1 200" and the request of an nginx line were not in the columns of the Odoo line (the nginx line stayed as plain text). Diagnosis: WERKZEUG_RE needs the Odoo tail (time, SQL count), which nginx does not have. Fix: NGINX_REQUEST_RE.
  - Symptom: the country of ERROR lines was one column to the right and that of CRITICAL lines three columns to the right. Diagnosis: the compensation of the level width was applied after the address, so it moved the request but not the country. Fix: the level is right-aligned in a fixed field.
- Safeguards and edge cases:
  - A line that does not match NGINX_REQUEST_RE (other request forms, error lines) keeps its display.
  - The Odoo lines move 4 columns to the right, as chosen by the user; the text of the Odoo messages that are not requests keeps its column (NUMBERS_BLOCK_WIDTH is adjusted).
  - A size of 100 kB or more (6 digits) still pushes the request by one column: not seen in the logs of this site.
  - nginx does not log the time of a request: to show it, add $request_time to the access log_format of nginx (not done by this program).
- Checks:
  - Rendering with the real Formatting on an Odoo request and on the nginx request of the same page: country at 44, address at 47, name at 77 (normal mode) or 63 (--min), HTTP code at 134 (120 with --min), request at 165 (151), size ending at the same column as the Odoo dash.
  - nginx-tools-tests/test_logs_merge.py: 9 tests OK.

### 1.116.20261029.225312 - nginx lines aligned with Odoo, key x, --log-nginx renamed, status bar without hidden-address text

- Title: the nginx lines take the columns of the Odoo lines (country, address, name); the option is renamed --log-nginx; the key x shows or hides the nginx lines; the status bar no longer says that the addresses are hidden.
- Reason: The nginx lines were not aligned with the Odoo lines: their address was not in the address column, so the country and the name moved. The status bar text "IP principales masquees (--show-ip)" was noise when the addresses are hidden. The option name had an extra "s" (--logs-nginx). An option to show the nginx lines was needed in the key menu.
- Changes:
  - Line.nginx_fields (new method): a nginx line (program "http") gets the level INFO, the database "nginx" and the logger "request" (13 characters, like "base werkzeug"). An error line gets the level of its [error] or [warn] tag and the logger "error". NGINX_ERROR_TAG_RE and NGINX_LEVELS (new constants).
  - The nginx lines use the journal program name "http" (4 characters, like "odoo"; apps/_logs_merge.py JOURNAL_PROGRAM), so their header columns are the same as the Odoo lines. Formatting.format_value is unchanged for the Odoo lines. Formatting.hidden_logger: the logger "request" of nginx is hidden with --min, as "werkzeug". The header keeps the request fields of an nginx request as for an Odoo request.
  - StatusBar.top_ips: returns nothing when the addresses are hidden (the text "top IP ... hidden (--show-ip)" is gone). StatusBar.summary adds the part only if it is not empty.
  - Option --log-nginx (renamed from --logs-nginx) and key LOG_NGINX of the configuration file (SCHEMA_CONFIG). Function stream_command: on a journal application the nginx logs are always read with the application stream when they exist (so that key x can show them at any time); BigBlueButton is unchanged.
  - Key x (MENU_KEYS "lognginx", new handler, new line in the key menu): shows or hides the nginx lines from the next line on. Hidden nginx lines are dropped in the consumer loop before any lookup or count (options "log_nginx" and "nginx_merged").
  - Start message: "+ nginx logs, merged in time order" with --log-nginx, otherwise "nginx logs read, hidden (key x shows them)".
  - Files touched: app-log-live.py, lang/app-log-live.fr.po (the --show-ip message removed, two messages added, LOG_NGINX in the list of configuration keys), doc/en/07-app-log-live.md and doc/fr/07-app-log-live.md (section rewritten), doc/en and doc/fr app-log-live.conf.example, nginx-tools-tests/test_logs_merge.py (alignment test added).
- Bugs fixed:
  - Symptom: a nginx line did not align with the Odoo lines (country and name shifted). Diagnosis: the nginx line had no level, so Formatting did not put its address in the address column; and the program name "nginx" is one character longer than "odoo", so the name was shifted by one column. Fix: nginx_fields, and the program name "http" (4 characters).
  - Symptom: "IP principales masquees (--show-ip)" in the status bar. Diagnosis: top_ips always returned a text when the addresses were hidden. Fix: top_ips returns nothing.
- Safeguards and edge cases:
  - Lines read while the nginx lines were hidden are not shown when key x turns them on: the stream is not restarted.
  - The request text of a nginx line does not line up with the GET of an Odoo request: Odoo shows a block of SQL and time numbers before the request, which nginx does not provide. Country, address and name are aligned.
  - An error line keeps the level width compensation of Odoo (ERROR is one character wider than INFO).
  - BigBlueButton (file journals): no merge and no gate; its nginx lines stay displayed.
- Checks:
  - py_compile OK; --version gives 1.116.20261029.225312 (dynamic).
  - Rendering check with the real Formatting: the country, the address and the name of an nginx request and of an Odoo request fall in the same columns (normal mode and --min).
  - nginx-tools-tests/test_logs_merge.py: 9 tests OK (including the alignment test).
  - Other suites: see the pull request.
- Action required: none. Optional: LOG_NGINX=yes in /etc/default/app-log-live.conf to show the nginx lines by default. Users of --logs-nginx (1.115): replace it with --log-nginx.

### 1.115.20261029.215532 - nginx logs merged with the application stream (--logs-nginx)

- Title: `--logs-nginx` adds the access and error logs of the site to the application stream, in time order, with the same date and time prefix.
- Reason: The nginx logs and the Odoo log were read in two windows. A request that failed on nginx (404, 502, a refused upload) could not be placed in time next to the Odoo message it caused. The request was for the nginx lines to have the same format and the same date as the Odoo lines.
- Changes:
  - app-log-live.py: new option --logs-nginx, and the key LOGS_NGINX of the configuration file (SCHEMA_CONFIG). New function nginx_log_files: the ACCESS_LOGS and ERROR_LOGS of the profile, in NGINX_DIR, existing files only. Function stream_command: with the option, it returns the command of apps/_logs_merge.py, which runs the application command after "--" and one tail per nginx file; --since, --until and -g are passed on (they apply to the nginx lines; the application lines are already filtered by journalctl). Function check_service: the idle-stream check also applies to a merged journal ("journalctl" in the command). main: a line at startup names the nginx files merged. New constant LOGS_MERGE. The --config help lists the new key.
  - apps/_logs_merge.py (new): merges the streams by time. Each nginx line receives the journal prefix "2026-10-29T21:52:03.000000-0400 host nginx: " in local time. Access log: the date of the request is removed from the text (it is in the prefix), as for the werkzeug lines of Odoo. Error log: the date and time at the start of the line are removed.
  - lang/app-log-live.fr.po: two new messages; the list of configuration keys in the --config help is updated.
  - nginx-tools-tests/test_logs_merge.py (new): 8 tests.
  - doc/en/07-app-log-live.md and doc/fr/07-app-log-live.md: new section "nginx logs in the same stream"; doc/en and doc/fr app-log-live.conf.example: key LOGS_NGINX.
- Bugs fixed: none.
- Safeguards and edge cases:
  - A silent stream is waited for APP_LOG_MERGE_WAIT seconds (2 by default), then it is "stalled": it is not waited for again until one of its lines arrives. A quiet nginx does not hold back the Odoo lines. Consequence: a nginx line that arrives after a stall can appear a little out of order (at most the waiting time).
  - A line whose time is unknown (traceback continuation, nginx line in an unknown format) takes the time of the previous line of its stream and is printed as it is.
  - Without the option, the command is unchanged. BigBlueButton (file journals): its nginx logs are still followed by tail, as before, unless --logs-nginx is given.
  - SIGTERM (sent when app-log-live stops) stops the merger and the commands it started; a closed output pipe ends the program without a message.
  - Python 3.8 compatible (the test test_aucune_fonction_posterieure_a_python_3_8 passes).
- Checks:
  - py_compile OK for app-log-live.py and apps/_logs_merge.py; --version gives 1.115.20261029.215532 (dynamic).
  - nginx-tools-tests/test_logs_merge.py: 8 tests OK (order of the two streams, prefix, local time, nginx error line, --grep / --since / --until on nginx only, line without time, dynamic --version, command built by stream_command with and without the option).
  - test_conventions, test_docs and test_i18n: all OK, except two checks of the CHANGELOG version: app-log-live.py (fixed by this entry) and odoo-warmup.py (code 1.36, first CHANGELOG entry 1.35; this change does not touch odoo-warmup.py).
  - Manual test on simulated logs (no Odoo server here): chronological order, the nginx line printed at its own time between two Odoo lines, the commands stopped on SIGTERM.
  - Not tested here: a real journalctl stream of an Odoo server.
- Action required: none. Optional: LOGS_NGINX=yes in /etc/default/app-log-live.conf to make the merge the default.

### 1.114.20261029.192022 - Status bar: top addresses, red alert once, status settings in the configuration file

- Title: the status bar names the three addresses with the most problem lines, gives one alert when it turns red, and the --buffer and --status-every settings can be kept in the configuration file.
- Reason: The status bar of 1.113 shows that something is wrong, but not where it comes from. The red colour was only visible in the bar, so an operator looking at another window could miss it. The two settings of the bar had to be given on the command line each time.
- Changes:
  - StatusBar.observe (function observe): counts, for each displayed line that is a problem (4xx, 5xx, SQL injection attempt, banned address), the first address of the line (new parameter ip). StatusBar.top_ips (new method): "top IP" followed by the three addresses with the most problems, as "ip (count)".
  - Privacy: the top addresses are shown only when the addresses are displayed (--show-ip, the H key). Otherwise the bar says that they are hidden (--show-ip). status_line reads the H key setting at each redraw, so the bar follows the key.
  - Alert (emit, in follow): the first time the bar is red since the last reset, one beep (sonner, same mode as --chime, whatever --chime is) and one red line "ALERT: the status bar turned red...". The alert is not repeated until Ctrl-T or g resets the counters (StatusBar.alerted).
  - Configuration: SCHEMA_CONFIG gets BUFFER (--buffer) and STATUS_EVERY (--status-every). They are read from /etc/default/app-log-live.conf, then from ~/.app-log-live.conf, and the command line keeps priority.
  - Files touched: app-log-live.py, lang/app-log-live.fr.po (3 new messages), nginx-tools-tests/test_app_log_live.py, doc/fr/07-app-log-live.md and doc/en/07-app-log-live.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - A line with no address (for example a line without a client address) is counted in the totals but not in the top addresses.
  - The alert is given once per period: a bar that stays red does not beep on each line.
  - The beep respects the terminal check of sonner: nothing is sent when the output is not a terminal (redirected output, tests).
  - Only the bar is affected by --hide-ip: the daily journal keeps the same content as before.
- Checks:
  - py_compile OK; --version displays 1.114.20261029.192022.
  - New unit test test_114_ip_principales_alerte_rouge_une_fois (see the verdict of the testeur agent in the pull request).
- Action required: none. Optional: add BUFFER=... and STATUS_EVERY=... to app-log-live.conf to change the defaults (200 and 100).

### 1.113.20261029.171832 - Real-time dashboard: status bar, refresh (f), print (P), key menu in order

- Title: a status bar in reverse video every N lines, the refresh of the last lines (f), their printing to a file (P), and the key menu sorted by short key.
- Reason: The program can run for several hours. Looking at the page after page of the stream to find the problems is not practical. A bar summarizing the recent problems (SQL injection attempts, 4xx and 5xx answers, banned addresses, slow requests) tells where to start an investigation. The keys of the menu (h) are listed by short key, the refresh of the last lines with the current options is a key of the menu like the toggles, and P prints the last lines (colors kept) to a file.
- Changes:
  - Status bar (class StatusBar, function status_line): printed after every N displayed lines (--status-every N, 100 by default, 0 = never). It counts since the last detailed report: SQL injection attempts (SQLI_RE, applied to the decoded URL: UNION SELECT, sleep/benchmark/extractvalue..., tautologies, stacked statements), 4xx and 5xx answers, addresses currently banned seen on the lines, slow requests (duration >= --slow) and the slowest one. Reset by Ctrl-T and g (key function). Reverse video (SGR 7), colour white (37, nothing to see), green (32, a little), yellow (33, to look at), red (31, investigate now). Thresholds in StatusBar.color(): red = 3 or more injections, 10 or more 5xx, 20 or more slow requests; yellow = one injection, one 5xx, one banned address, 5 or more slow requests, 100 or more 4xx; green = a 4xx or a slow request.
  - Buffer (function paint): the displayed lines are kept with their source data (results and pays) in a deque of --buffer N lines (200 by default, 0 = none). emit() is split into compose() (rendering and banned label), paint() (writes and keeps) and emit() (counting, status bar, chime).
  - f key (refresh_lines): the buffered lines are displayed again with the current options (IP, DNS, names, highlight, --only...). They are not counted again and not written again to the daily journal (output.active is set to False during the refresh).
  - P key (print_lines): asks the number of lines (default: all of the buffer) and the file name (default: app-log-live-print-YYYYMMDD-HHMMSS.log in the log folder). The file is created with O_EXCL and mode 600, the colours are kept, the lines are the real ones (not anonymized).
  - Y key: the latency report (LATENCY.lines) moved from the key P, which is now the print key. MENU_KEYS: Y latency, P print, f refresh.
  - Key menu (h): the short keys are sorted alphabetically (case-insensitive, lowercase first on equal letters), in the options section and in the Others section. The f, P and Y entries are added.
  - Options: --buffer N and --status-every N (new), validated (zero or positive).
  - Ctrl-G and Ctrl-T also print a line saying that the counters of the status bar were reset.
  - Files touched: app-log-live.py, lang/app-log-live.fr.po (French of the new messages and help), doc/fr/07-app-log-live.md and doc/en/07-app-log-live.md, nginx-tools-tests/test_app_log_live.py (key test updated: P is print, Y is latency; new test of the status bar and of the SQL injection detection), CHANGELOG.md.
- Bugs fixed: none. Note: the key P was documented as latency; it is now Y (see above).
- Safeguards and edge cases:
  - Lines replayed by f are not counted in the status bar, the statistics or the record (test recording).
  - Lines without a stored source (reminders of a visitor, deferred lines) are not refreshable: they are skipped by f.
  - P refuses to overwrite an existing file (O_EXCL); a write error is shown, the program continues.
  - The status bar colours are not anonymized (no address is shown in the bar).
  - A bar without any line counted is white.
- Checks:
  - py_compile OK; the new unit tests pass (test_113_barre_d_etat_couleur_et_injection_sql and test_touches_g_et_p_reliees updated).
  - Full module test_app_log_live: see the verdict of the run below.
- Action required: note the new key assignment: P prints, Y shows the latency report. To have a status bar at another interval, use --status-every N; to keep more or fewer lines for f and P, use --buffer N.

### 1.112.20261029.165811 - Time window, journalctl options, country filters, fractions of a day

- Title: --since / -S, --until / -U, --utc, -n, --no-hostname, -g / --grep, --country, --exclude-country; --days accepts fractions (0.1 = 2.4 hours).
- Reason: The administrator wanted to follow the Odoo journal for a precise period (for example the last 0.1 day) and to use the options of journalctl (-S, -U, -n, --utc, --no-hostname...). He also wanted to show or hide the addresses of one country, which the program did not offer.
- Changes:
  - --days is now a decimal number (type float). 0 keeps the whole history; a whole number of days keeps the form "--since -N days" sent to journalctl, a fraction is sent as an epoch.
  - -S / --since TIME and -U / --until TIME (new function parse_time): "now", "today", "yesterday", "@EPOCH", "HH:MM[:SS]", "YYYY-MM-DD [HH:MM[:SS]] [Z or +HH:MM]", relative values ("-2h", "+1 day", "0.5 hour", "3 days ago", units s, min, h, d, w and long forms). A date alone is the start of its day, and the start of the next day for --until.
  - --utc: the times of the log lines and the times given without a time zone are in UTC (default: local time). Parsed in Line._analyze.
  - -n is an alias of --lines (same meaning as journalctl -n).
  - --no-hostname (journalctl option, and the host name is left out of the header of the line; the lines without host are read: JOURNAL_RE host now optional).
  - -g / --grep REGEX (new functions window_keep): the message of each line must match; case-insensitive unless the pattern has an uppercase letter (journalctl smart case). Also passed to journalctl with --case-sensitive for the live stream.
  - --country CC,CC and --exclude-country CC,CC (new function country_keep): filter on the country of the FIRST address of the line (the client), the same address as --exclude-ip. Repeatable, two-letter codes, validated.
  - -f / --follow and --no-pager: accepted for journalctl compatibility, no effect (the live stream is the default, the output is never paged).
  - --until stops the live stream when a line reaches that time (the stream is in order).
  - --days + --since together are refused; --until must be later than --since.
  - Config key DAYS is read as a decimal number.
  - journal_epoch, days_window, journal_options, read_history (new arguments since and until), stream_command, main (filter setup and eprint of the active filters).
  - Files touched: app-log-live.py, lang/app-log-live.fr.po (French of the new messages and help; the old --days help entry removed), nginx-tools-tests/test_app_log_live.py (two new tests), CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - A line without time header (Python trace, BigBlueButton) follows the time window of the previous timed line; --grep is tested on every line.
  - A timed line without address is hidden by --country and kept by --exclude-country; an address of unknown country is hidden by --country and kept by --exclude-country.
  - Lines with an address whose country lookup is still pending when the line is shown (WAIT_DELAY) follow the rule for unknown countries.
  - The --days message of the history keeps its wording; the file-based history (Odoo logfile) filters on the epoch of each line.
  - --since with a value in the future gives no line (no error).
- Checks:
  - py_compile OK; --help lists the new options in alphabetical order (aide triée par le formateur).
  - Manual checks of parse_time (formats, relative values, --utc, invalid values), of the journal line parsing with and without host, of window_keep and country_keep, and of the journalctl command built by stream_command.
  - Unit tests: nginx-tools-tests/test_app_log_live.py, 151 tests run, one failure: test_colonnes_jamais_tassees_pays_noms_anonymises_et_souligne_tous_les_n. The same failure exists without this change (checked on the previous version): not caused by 1.112.
  - test_i18n: the catalogue of app-log-live is complete; the failure of nginx-hardening (bash catalogue) is not related to this program.
  - test_conventions (order of the versions in CHANGELOG.md): the 1.112.20261028.214122 section of this program was already placed after 1.111.20261028.225404; not changed here.
- Action required: none. Example: app-log-live.py -S '-2h' --utc -n 500 ; app-log-live.py --exclude-country US,CN ; app-log-live.py --days 0.1 --no-follow.

### 1.112.20261028.214122 - --menu: English programs translate the menu and its help through their catalogue

- Title: --menu: English programs translate the menu and its help through their catalogue.
- Reason: With --lang en, the --menu help and the menu entries were partly in French: the catalogue tests (test_i18n) and the English help test (test_web_monitor) failed.
- Changes:
  - The menu entries and the --menu help are written in English in the code; their French text is in lang/app-log-live.py.fr.po (msgid = English text, msgstr = French).
  - apps/_menu.py: menu() takes traduire (the program's translator) and langue (the program's display language). The menu labels and its messages follow the program's language, not only NGINX_TOOLS_I18N_LANGUE.
  - nginx-tools-tests/test_config_defaut.py: --menu is an action (CLI only, like --backup), excluded from the check of the configuration model.
  - Files: app-log-live.py, lang/app-log-live.py.fr.po, apps/_menu.py, nginx-tools-tests/test_config_defaut.py, CHANGELOG.md.
- Bugs fixed: symptom: test_i18n reported French text in the code of this English program. Diagnosis: the new menu strings were French in the code, but this program's code is English and its texts are translated through lang/. Correction: English strings plus catalogue entries.
- Safeguards and edge cases: the menu labels, its confirmation and cancel messages follow the language of the program; the entries still run the same options as before.
- Checks: test_i18n (catalogues), test_menu, test_config_defaut, the English help test of this program where it exists.
- Action required: none.

### 1.111.20261028.225404 - --keep-ip: the old name of --show-ip works again

- Title: --keep-ip (old name of --show-ip) had no effect since the address became hidden by default (1.107); it now shows the IP address again.
- Reason: The test of the default address (test_ip_gardee_par_defaut_hide_ip_et_libelle_court) found that --keep-ip did not show the IP, and the default expectations of the tests were out of date.
- Changes:
  - --keep-ip is the same option as --show-ip (hidden from --help, as before).
  - nginx-tools-tests/test_app_log_live.py: tests that read addresses ask for --show-ip (the default is now masked, HIDE_IP=yes); the default test checks the masked default; the summary wording of « Adresses à bannir » and the web-monitor reasons are the current ones; the key-menu test waits for the current prompts with a wide terminal.
  - Files: app-log-live.py, nginx-tools-tests/test_app_log_live.py, CHANGELOG.md.
- Bugs fixed: symptom: --keep-ip accepted but ignored, so the address stayed hidden. Diagnosis: the option stored a value that nothing read. Correction: same destination as --show-ip.
- Safeguards and edge cases: the default (masked address) is unchanged; --show-ip and --hide-ip keep their meaning.
- Checks: test_app_log_live (one test still fails: column alignment, the order of the lines in the output, see the pull request).
- Action required: none.

### 1.111.20261028.211449 - --menu: interactive menu of the usual operations

- Title: New option --menu: a menu (dialog when installed, text otherwise) for the usual operations of app-log-live.py.
- Reason: Operations were only reachable through command-line options. The menu offers them by number, shows the configuration read, and asks for confirmation before operations that change the system.
- Changes:
  - New option --menu (terminal required). Entries: suivi en direct, diagnostic, modules Odoo, derniers messages; configuration read (c or the menu item); change log (--changelog); quit.
  - Each entry runs this program again with the options received on the command line (except --menu) plus its own option. Entries that change the system ask for confirmation first.
  - Shared library apps/_menu.py (new): dialog when installed, text menu otherwise, with a note to install dialog.
  - Help: --menu listed in alphabetical order. --help, --version and --changelog keep their priority over --menu.
  - Files: app-log-live.py, apps/_menu.py (new), nginx-tools-tests/test_menu.py (new), CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - Without a terminal, --menu refuses with an error and exit code 1; nothing is run.
  - The menu relaunches the program only; root checks, locks and confirmations stay those of the operation itself.
- Checks:
  - test_menu: --menu listed in the help, refused without a terminal.
  - Manual test in a pseudo-terminal (text menu and stand-in dialog) on read-only entries.
  - Other tests of the program and conventions: see the pull request.
- Action required: none. To get the graphical menu: sudo apt install dialog.

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

### 1.8.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: none.
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

### 1.7.20261028.214122 - --menu: English programs translate the menu and its help through their catalogue

- Title: --menu: English programs translate the menu and its help through their catalogue.
- Reason: With --lang en, the --menu help and the menu entries were partly in French: the catalogue tests (test_i18n) and the English help test (test_web_monitor) failed.
- Changes:
  - The menu entries and the --menu help are written in English in the code; their French text is in lang/host-perf-audit.py.fr.po (msgid = English text, msgstr = French).
  - apps/_menu.py: menu() takes traduire (the program's translator) and langue (the program's display language). The menu labels and its messages follow the program's language, not only NGINX_TOOLS_I18N_LANGUE.
  - nginx-tools-tests/test_config_defaut.py: --menu is an action (CLI only, like --backup), excluded from the check of the configuration model.
  - Files: host-perf-audit.py, lang/host-perf-audit.py.fr.po, apps/_menu.py, nginx-tools-tests/test_config_defaut.py, CHANGELOG.md.
- Bugs fixed: symptom: test_i18n reported French text in the code of this English program. Diagnosis: the new menu strings were French in the code, but this program's code is English and its texts are translated through lang/. Correction: English strings plus catalogue entries.
- Safeguards and edge cases: the menu labels, its confirmation and cancel messages follow the language of the program; the entries still run the same options as before.
- Checks: test_i18n (catalogues), test_menu, test_config_defaut, the English help test of this program where it exists.
- Action required: none.

### 1.6.20261028.211449 - --menu: interactive menu of the usual operations

- Title: New option --menu: a menu (dialog when installed, text otherwise) for the usual operations of host-perf-audit.py.
- Reason: Operations were only reachable through command-line options. The menu offers them by number, shows the configuration read, and asks for confirmation before operations that change the system.
- Changes:
  - New option --menu (terminal required). Entries: mesure (60 s), réglages sans risque (--apply); configuration read (c or the menu item); change log (--changelog); quit.
  - Each entry runs this program again with the options received on the command line (except --menu) plus its own option. Entries that change the system ask for confirmation first.
  - Shared library apps/_menu.py (new): dialog when installed, text menu otherwise, with a note to install dialog.
  - Help: --menu listed in alphabetical order. --help, --version and --changelog keep their priority over --menu.
  - Files: host-perf-audit.py, apps/_menu.py (new), nginx-tools-tests/test_menu.py (new), CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - Without a terminal, --menu refuses with an error and exit code 1; nothing is run.
  - The menu relaunches the program only; root checks, locks and confirmations stay those of the operation itself.
- Checks:
  - test_menu: --menu listed in the help, refused without a terminal.
  - Manual test in a pseudo-terminal (text menu and stand-in dialog) on read-only entries.
  - Other tests of the program and conventions: see the pull request.
- Action required: none. To get the graphical menu: sudo apt install dialog.

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

### 1.13.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: none.
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

### 1.12.20261028.214122 - --menu: English programs translate the menu and its help through their catalogue

- Title: --menu: English programs translate the menu and its help through their catalogue.
- Reason: With --lang en, the --menu help and the menu entries were partly in French: the catalogue tests (test_i18n) and the English help test (test_web_monitor) failed.
- Changes:
  - The menu entries and the --menu help are written in English in the code; their French text is in lang/odoo-chat-post.py.fr.po (msgid = English text, msgstr = French).
  - apps/_menu.py: menu() takes traduire (the program's translator) and langue (the program's display language). The menu labels and its messages follow the program's language, not only NGINX_TOOLS_I18N_LANGUE.
  - nginx-tools-tests/test_config_defaut.py: --menu is an action (CLI only, like --backup), excluded from the check of the configuration model.
  - Files: odoo-chat-post.py, lang/odoo-chat-post.py.fr.po, apps/_menu.py, nginx-tools-tests/test_config_defaut.py, CHANGELOG.md.
- Bugs fixed: symptom: test_i18n reported French text in the code of this English program. Diagnosis: the new menu strings were French in the code, but this program's code is English and its texts are translated through lang/. Correction: English strings plus catalogue entries.
- Safeguards and edge cases: the menu labels, its confirmation and cancel messages follow the language of the program; the entries still run the same options as before.
- Checks: test_i18n (catalogues), test_menu, test_config_defaut, the English help test of this program where it exists.
- Action required: none.

### 1.11.20261028.211449 - --menu: interactive menu of the usual operations

- Title: New option --menu: a menu (dialog when installed, text otherwise) for the usual operations of odoo-chat-post.py.
- Reason: Operations were only reachable through command-line options. The menu offers them by number, shows the configuration read, and asks for confirmation before operations that change the system.
- Changes:
  - New option --menu (terminal required). Entries: catalogue, création à blanc, création des canaux, compte du robot; configuration read (c or the menu item); change log (--changelog); quit.
  - Each entry runs this program again with the options received on the command line (except --menu) plus its own option. Entries that change the system ask for confirmation first.
  - Shared library apps/_menu.py (new): dialog when installed, text menu otherwise, with a note to install dialog.
  - Help: --menu listed in alphabetical order. --help, --version and --changelog keep their priority over --menu.
  - Files: odoo-chat-post.py, apps/_menu.py (new), nginx-tools-tests/test_menu.py (new), CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - Without a terminal, --menu refuses with an error and exit code 1; nothing is run.
  - The menu relaunches the program only; root checks, locks and confirmations stay those of the operation itself.
- Checks:
  - test_menu: --menu listed in the help, refused without a terminal.
  - Manual test in a pseudo-terminal (text menu and stand-in dialog) on read-only entries.
  - Other tests of the program and conventions: see the pull request.
- Action required: none. To get the graphical menu: sudo apt install dialog.

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

### 1.8.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: none.
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

### 1.7.20261028.214122 - --menu: English programs translate the menu and its help through their catalogue

- Title: --menu: English programs translate the menu and its help through their catalogue.
- Reason: With --lang en, the --menu help and the menu entries were partly in French: the catalogue tests (test_i18n) and the English help test (test_web_monitor) failed.
- Changes:
  - The menu entries and the --menu help are written in English in the code; their French text is in lang/odoo-docs.py.fr.po (msgid = English text, msgstr = French).
  - apps/_menu.py: menu() takes traduire (the program's translator) and langue (the program's display language). The menu labels and its messages follow the program's language, not only NGINX_TOOLS_I18N_LANGUE.
  - nginx-tools-tests/test_config_defaut.py: --menu is an action (CLI only, like --backup), excluded from the check of the configuration model.
  - Files: odoo-docs.py, lang/odoo-docs.py.fr.po, apps/_menu.py, nginx-tools-tests/test_config_defaut.py, CHANGELOG.md.
- Bugs fixed: symptom: test_i18n reported French text in the code of this English program. Diagnosis: the new menu strings were French in the code, but this program's code is English and its texts are translated through lang/. Correction: English strings plus catalogue entries.
- Safeguards and edge cases: the menu labels, its confirmation and cancel messages follow the language of the program; the entries still run the same options as before.
- Checks: test_i18n (catalogues), test_menu, test_config_defaut, the English help test of this program where it exists.
- Action required: none.

### 1.6.20261028.211449 - --menu: interactive menu of the usual operations

- Title: New option --menu: a menu (dialog when installed, text otherwise) for the usual operations of odoo-docs.py.
- Reason: Operations were only reachable through command-line options. The menu offers them by number, shows the configuration read, and asks for confirmation before operations that change the system.
- Changes:
  - New option --menu (terminal required). Entries: vérification, essai (--dry-run), publication; configuration read (c or the menu item); change log (--changelog); quit.
  - Each entry runs this program again with the options received on the command line (except --menu) plus its own option. Entries that change the system ask for confirmation first.
  - Shared library apps/_menu.py (new): dialog when installed, text menu otherwise, with a note to install dialog.
  - Help: --menu listed in alphabetical order. --help, --version and --changelog keep their priority over --menu.
  - Files: odoo-docs.py, apps/_menu.py (new), nginx-tools-tests/test_menu.py (new), CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - Without a terminal, --menu refuses with an error and exit code 1; nothing is run.
  - The menu relaunches the program only; root checks, locks and confirmations stay those of the operation itself.
- Checks:
  - test_menu: --menu listed in the help, refused without a terminal.
  - Manual test in a pseudo-terminal (text menu and stand-in dialog) on read-only entries.
  - Other tests of the program and conventions: see the pull request.
- Action required: none. To get the graphical menu: sudo apt install dialog.

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

### 1.19.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: none.
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

### 1.18.20261028.214122 - --menu: English programs translate the menu and its help through their catalogue

- Title: --menu: English programs translate the menu and its help through their catalogue.
- Reason: With --lang en, the --menu help and the menu entries were partly in French: the catalogue tests (test_i18n) and the English help test (test_web_monitor) failed.
- Changes:
  - The menu entries and the --menu help are written in English in the code; their French text is in lang/odoo-mail-retry.py.fr.po (msgid = English text, msgstr = French).
  - apps/_menu.py: menu() takes traduire (the program's translator) and langue (the program's display language). The menu labels and its messages follow the program's language, not only NGINX_TOOLS_I18N_LANGUE.
  - nginx-tools-tests/test_config_defaut.py: --menu is an action (CLI only, like --backup), excluded from the check of the configuration model.
  - Files: odoo-mail-retry.py, lang/odoo-mail-retry.py.fr.po, apps/_menu.py, nginx-tools-tests/test_config_defaut.py, CHANGELOG.md.
- Bugs fixed: symptom: test_i18n reported French text in the code of this English program. Diagnosis: the new menu strings were French in the code, but this program's code is English and its texts are translated through lang/. Correction: English strings plus catalogue entries.
- Safeguards and edge cases: the menu labels, its confirmation and cancel messages follow the language of the program; the entries still run the same options as before.
- Checks: test_i18n (catalogues), test_menu, test_config_defaut, the English help test of this program where it exists.
- Action required: none.

### 1.17.20261028.211449 - --menu: interactive menu of the usual operations

- Title: New option --menu: a menu (dialog when installed, text otherwise) for the usual operations of odoo-mail-retry.py.
- Reason: Operations were only reachable through command-line options. The menu offers them by number, shows the configuration read, and asks for confirmation before operations that change the system.
- Changes:
  - New option --menu (terminal required). Entries: courriels récents, adresses invalides, 20 derniers envoyés; configuration read (c or the menu item); change log (--changelog); quit.
  - Each entry runs this program again with the options received on the command line (except --menu) plus its own option. Entries that change the system ask for confirmation first.
  - Shared library apps/_menu.py (new): dialog when installed, text menu otherwise, with a note to install dialog.
  - Help: --menu listed in alphabetical order. --help, --version and --changelog keep their priority over --menu.
  - Files: odoo-mail-retry.py, apps/_menu.py (new), nginx-tools-tests/test_menu.py (new), CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - Without a terminal, --menu refuses with an error and exit code 1; nothing is run.
  - The menu relaunches the program only; root checks, locks and confirmations stay those of the operation itself.
- Checks:
  - test_menu: --menu listed in the help, refused without a terminal.
  - Manual test in a pseudo-terminal (text menu and stand-in dialog) on read-only entries.
  - Other tests of the program and conventions: see the pull request.
- Action required: none. To get the graphical menu: sudo apt install dialog.

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

### 1.37.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: none.
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

### 1.35.20261028.222437 - Messages in English only: no French duplicate lines; catalogue entries updated

- Title: English messages only (the French text comes from lang/odoo-warmup.fr.po); stale catalogue entries updated.
- Reason: The English program printed some messages twice (English then French), and its catalogue had entries for older texts. The catalogue test (test_i18n) reported them.
- Changes:
  - Removed the French duplicate lines of the warm-up unit file, the Odoo-not-listening wait, the unreadable configuration file warning, the several-units error, the unit found message, and the no-process warning.
  - lang/odoo-warmup.fr.po: entries for the English messages now printed; the systemd unit texts and the --systemd-install / --systemd-remove help are updated to the current code text.
  - Files: odoo-warmup.py, lang/odoo-warmup.fr.po, CHANGELOG.md.
- Bugs fixed: symptom: each message appeared in French too, and some French texts had no English source. Diagnosis: bilingual lines written by hand in the code, and catalogue entries for texts that had changed. Correction: English only in the code, catalogue updated.
- Safeguards and edge cases: the French display is unchanged in the text; the systemd unit content is unchanged apart from its comment wording.
- Checks: test_i18n (catalogues of the Python programs).
- Action required: none.

### 1.36.20261028.214122 - --menu: English programs translate the menu and its help through their catalogue

- Title: --menu: English programs translate the menu and its help through their catalogue.
- Reason: With --lang en, the --menu help and the menu entries were partly in French: the catalogue tests (test_i18n) and the English help test (test_web_monitor) failed.
- Changes:
  - The menu entries and the --menu help are written in English in the code; their French text is in lang/odoo-warmup.py.fr.po (msgid = English text, msgstr = French).
  - apps/_menu.py: menu() takes traduire (the program's translator) and langue (the program's display language). The menu labels and its messages follow the program's language, not only NGINX_TOOLS_I18N_LANGUE.
  - nginx-tools-tests/test_config_defaut.py: --menu is an action (CLI only, like --backup), excluded from the check of the configuration model.
  - Files: odoo-warmup.py, lang/odoo-warmup.py.fr.po, apps/_menu.py, nginx-tools-tests/test_config_defaut.py, CHANGELOG.md.
- Bugs fixed: symptom: test_i18n reported French text in the code of this English program. Diagnosis: the new menu strings were French in the code, but this program's code is English and its texts are translated through lang/. Correction: English strings plus catalogue entries.
- Safeguards and edge cases: the menu labels, its confirmation and cancel messages follow the language of the program; the entries still run the same options as before.
- Checks: test_i18n (catalogues), test_menu, test_config_defaut, the English help test of this program where it exists.
- Action required: none.

### 1.35.20261028.211449 - --menu: interactive menu of the usual operations

- Title: New option --menu: a menu (dialog when installed, text otherwise) for the usual operations of odoo-warmup.py.
- Reason: Operations were only reachable through command-line options. The menu offers them by number, shows the configuration read, and asks for confirmation before operations that change the system.
- Changes:
  - New option --menu (terminal required). Entries: préchauffage, préchauffage au démarrage (installation et retrait); configuration read (c or the menu item); change log (--changelog); quit.
  - Each entry runs this program again with the options received on the command line (except --menu) plus its own option. Entries that change the system ask for confirmation first.
  - Shared library apps/_menu.py (new): dialog when installed, text menu otherwise, with a note to install dialog.
  - Help: --menu listed in alphabetical order. --help, --version and --changelog keep their priority over --menu.
  - Files: odoo-warmup.py, apps/_menu.py (new), nginx-tools-tests/test_menu.py (new), CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - Without a terminal, --menu refuses with an error and exit code 1; nothing is run.
  - The menu relaunches the program only; root checks, locks and confirmations stay those of the operation itself.
- Checks:
  - test_menu: --menu listed in the help, refused without a terminal.
  - Manual test in a pseudo-terminal (text menu and stand-in dialog) on read-only entries.
  - Other tests of the program and conventions: see the pull request.
- Action required: none. To get the graphical menu: sudo apt install dialog.

### 1.34.20261027.125500 - Warm-up delay in an environment file

- Title: The delay is read at each start from /etc/default/odoo-warmup-NAME (WARMUP_DELAY=SECONDS): change it there, no reinstall.
- Reason: Changing the delay meant reinstalling the unit; a value in a file, read by systemd, is simpler to change on a server.
- Changes:
  - warmup_env_path(), delay_of_env_file(): the environment file and its WARMUP_DELAY.
  - systemd_content(): Environment=WARMUP_DELAY=120 (default), EnvironmentFile=- the file (it overrides the default), ExecStartPre=/bin/sleep ${WARMUP_DELAY}.
  - systemd_install_unit(): writes the file when --delay is given, or when it does not exist yet; otherwise keeps the value of the file.
  - --delay (with --systemd-install) is written to the file; negative values refused.
  - Files: odoo-warmup.py, nginx-tools-tests/test_odoo_warmup.py, CHANGELOG.md.
- Bugs fixed:
  - Symptom: a new delay needed a reinstall of the unit.
  - Diagnosis: the delay was written in the unit file.
  - Correction: the delay is in the environment file, read at each start.
- Safeguards and edge cases:
  - The file is not removed by --systemd-remove (it keeps the delay for a later install).
  - A missing or invalid value falls back to 120 s.
  - No daemon-reload is needed after a change to the file.
- Checks:
  - py_compile; test suite test_odoo_warmup (20 tests): file written, kept at a second install, changed by hand, negative value refused.
- Action required: none. To change the delay on the server: edit /etc/default/odoo-warmup-erplibre_erplibre (WARMUP_DELAY=30) and start the warm-up unit or restart erplibre_erplibre.service.

### 1.33.20261027.124500 - --delay: warm-up delay chosen on the command line

- Title: --delay SECONDS sets the delay before the warm-up in the unit installed by --systemd-install (default 120 s).
- Reason: The 120 s delay must be changed temporarily (slow SATA disks, tests) without editing the program.
- Changes:
  - --delay SECONDS (option, sorted with the others); used only with --systemd-install; negative values refused.
  - systemd_content() and systemd_install_unit() take the delay; the unit is written with ExecStartPre=/bin/sleep DELAY.
  - The directory of the units is created if it is missing.
  - Files: odoo-warmup.py, nginx-tools-tests/test_odoo_warmup.py, CHANGELOG.md.
- Bugs fixed:
  - Symptom: the unit could not be written when the systemd directory did not exist ("No such file or directory").
  - Diagnosis: the install of 1.32 did not create the directory, unlike the former drop-in.
  - Correction: os.makedirs of the directory before writing.
- Safeguards and edge cases:
  - The delay is written in the unit: to change it, reinstall with --delay (the unit is replaced).
  - --delay without --systemd-install has no effect.
- Checks:
  - py_compile; test suite test_odoo_warmup (20 tests), including --delay 30 and --delay -5.
- Action required: none. To change the delay for a test: sudo python3 /opt/rlq-admin-tools/odoo-warmup.py --systemd-install --service erplibre_erplibre.service --delay 30, then restart the unit to test; reinstall with the default (no --delay) to restore 120 s.

### 1.32.20261027.121500 - --systemd-install makes a separate unit, not a drop-in

- Title: --systemd-install installs odoo-warmup-NAME.service, which runs the warm-up 120 s after each start of the Odoo unit; the former drop-in with ExecStartPost is removed.
- Reason: The ExecStartPost of the drop-in made the start of erplibre_erplibre.service wait (start timeout after 90 s, restart loop). The warm-up must not be part of the start of the Odoo unit.
- Changes:
  - warmup_unit_path(): /etc/systemd/system/odoo-warmup-NAME.service (NAME = the unit without .service).
  - systemd_content(): Type=oneshot unit, ExecStartPre=/bin/sleep 120 (WARMUP_DELAY), ExecStart the warm-up with --wait, Requires= and After= the Odoo unit, WantedBy= the Odoo unit.
  - remove_dropin_ancien(): removes the former drop-in (dropin_path) at install and at removal.
  - systemd_install_unit(): writes the unit, daemon-reload, systemctl enable (not in tests).
  - systemd_remove_unit(): disables and removes the unit and the former drop-in.
  - Files: odoo-warmup.py, nginx-tools-tests/test_odoo_warmup.py, CHANGELOG.md.
- Bugs fixed:
  - Symptom: start of Odoo timed out (90 s), the unit was killed and restarted in a loop, while the warm-up ran at each start.
  - Diagnosis: ExecStartPost of the drop-in is part of the start job of the Odoo unit.
  - Correction: the warm-up runs in its own unit, after the start.
- Safeguards and edge cases:
  - The Odoo unit is not changed by the warm-up.
  - Without NGINX_TOOLS_SYSTEMD_DIR, daemon-reload and systemctl enable/disable run; in tests they do not.
- Checks:
  - py_compile; test suite test_odoo_warmup (19 tests), the install test checks the unit, the removal of the former drop-in and the removal.
- Action required: on the server, run --systemd-install --service erplibre_erplibre.service as root, then systemctl start odoo-warmup-erplibre_erplibre.service to test.

### 1.31.20261025.224500 - Redirection of a survey page not followed

- Title: For an optional page (survey), a redirection (303) is not followed: /en_CA/survey, which does not exist, is no longer requested.
- Reason: The log shows GET /survey (303), then GET /en_CA/survey (404) at once: the client followed the redirection of the survey page to its language version. The 1.30 diagnosis (the hreflang alternates) was wrong: the 1.30 change did not stop the request.
- Changes:
  - _SansRedirection: redirection handler that returns the 3xx as the answer.
  - Client.request_(path, suivre=True): suivre=False uses an opener without redirection.
  - load_page(): suivre is False for the optional pages (surveys).
  - Test: fake server redirects /survey to /en_CA/survey; /en_CA/survey must not be requested.
  - Files: odoo-warmup.py, nginx-tools-tests/test_odoo_warmup.py, CHANGELOG.md.
- Bugs fixed:
  - Symptom: 404 on /en_CA/survey at every run, after the 303 on /survey.
  - Diagnosis: urllib followed the 303 to the language version of the survey page.
  - Correction: no redirection is followed for an optional page; the other pages are unchanged (their redirections are followed, as before).
- Safeguards and edge cases:
  - Only the optional (survey) pages are concerned; the redirections of /web/login and /event are still followed.
  - The 303 counts as an answer below 400, so the survey page is not reported as a failure.
- Checks:
  - py_compile; test suite test_odoo_warmup (19 tests).
- Action required: none.

### 1.30.20261025.223900 - /survey back by default; no language versions of a survey page

- Title: /survey is a default page again, but its language versions (/en_CA/survey, /fr/survey...) are not requested.
- Reason: /survey exists on Odoo 18 CE; /en_CA/survey does not (404). The hreflang alternates of the pages announced /en_CA/survey, which the warm-up requested at every run. The 1.29 change removed the page itself, which was wrong.
- Changes:
  - DEFAULT_PAGES: /, /web/login, /event, /survey (restored).
  - language_variants(): returns no variant for an optional page (survey).
  - Example configuration files (doc/fr and doc/en) restored as before 1.29.
  - Tests: default pages include /survey; a survey page gives no language variant.
  - Files: odoo-warmup.py, nginx-tools-tests/test_odoo_warmup.py, doc/fr/odoo-warmup.conf.example, doc/en/odoo-warmup.conf.example, CHANGELOG.md.
- Bugs fixed:
  - Symptom: 404 on /en_CA/survey at every run (the log shows 303 on /survey, then 404 on /en_CA/survey).
  - Diagnosis: the alternates of the pages list /en_CA/survey, and the warm-up followed them.
  - Correction: no language version of a survey page is requested.
- Safeguards and edge cases:
  - The survey page itself is still requested and its failure is still only noted (optional).
  - Survey links (/survey/start/...) are still followed.
- Checks:
  - py_compile; test suite test_odoo_warmup (18 tests).
- Action required: none. The version 1.29 entry is superseded by this one.

### 1.29.20261025.223329 - No default survey page

- Title: /survey is no longer a default public page; the survey links found in the pages are still followed.
- Reason: The Odoo site has no /survey page (404 on /en_CA/survey and /survey); the warm-up requested it at every run.
- Changes:
  - DEFAULT_PAGES: /, /web/login, /event.
  - Example configuration files (doc/fr and doc/en): PAGES without /survey.
  - Test: the optional survey test sets PAGES=/,/survey explicitly.
  - Files: odoo-warmup.py, doc/fr/odoo-warmup.conf.example, doc/en/odoo-warmup.conf.example, nginx-tools-tests/test_odoo_warmup.py, CHANGELOG.md.
- Bugs fixed:
  - Symptom: a 404 on /survey at every run, shown as optional.
  - Diagnosis: the default list still contained /survey.
  - Correction: removed from the default list.
- Safeguards and edge cases:
  - A survey that is in PAGES (configuration) is still requested and reported as optional.
  - Survey links (/survey/start/...) found in the pages are still followed and never counted as failures.
- Checks:
  - py_compile; test suite test_odoo_warmup (17 tests).
- Action required: if /etc/default/odoo-warmup-pages.conf (or the PAGES key of your configuration) lists /survey, remove that line.

### 1.28.20261025.221900 - Start by systemd: detection waits for Odoo to listen

- Title: Started by the systemd drop-in, the warm-up waits up to 120 s for Odoo to listen before it chooses the port; the systemd options do not run the detection.
- Reason: The ExecStartPost of the drop-in starts the warm-up right after the start of erplibre_erplibre.service, while Odoo is still loading its modules. The detection found no listening port, fell back to 8069 and stopped; the Odoo log shows only the two first requests.
- Changes:
  - detect_odoo_url(attente): polls the candidate ports every 2 s until one is listening or the wait ends (DETECTION_WAIT = 120 s; message printed once).
  - --systemd-install and --systemd-remove do not run the detection and do not need Odoo.
  - Files: odoo-warmup.py, CHANGELOG.md.
- Bugs fixed:
  - Symptom: with the drop-in, the warm-up requests only /web/login and /en_CA/web/login, then stops (manual run: all pages).
  - Diagnosis: the detection runs once at the start, before the port is bound.
  - Correction: wait for the port.
- Safeguards and edge cases:
  - Nothing listening after 120 s: 8069 as before.
  - A manual run with Odoo already up is unchanged (the first poll finds the ports).
- Checks:
  - py_compile; test suite test_odoo_warmup (17 tests).
- Action required: check the journal of the warm-up unit (journalctl -u odoo-warmup-run) after the next restart of erplibre_erplibre.service, and send it if the warm-up still stops early.

### 1.27.20261025.220011 - Odoo processes recognised by the ERPlibre path too

- Title: A Python process is an Odoo process if its command line contains odoo or erplibre (not only odoo).
- Reason: On the server, the service erplibre_erplibre.service starts run.sh, which starts Python with the ERPlibre path; ExecStart carries no port. The UID of this Python process gives the ports, but the process was not recognised when its command line has no odoo word.
- Changes:
  - est_processus_odoo(): common test for the Python processes of Odoo, used by odoo_uids(), odoo_units() and commandes_odoo().
  - Files: odoo-warmup.py, nginx-tools-tests/test_odoo_warmup.py.
- Bugs fixed:
  - Symptom: no Odoo UID and no unit found, so no port from the owner of the process (no port detected).
  - Diagnosis: the match on the word odoo alone; the ERPlibre command line does not always contain it.
  - Correction: the match also accepts erplibre.
- Safeguards and edge cases:
  - bash processes are not matched: python is required.
  - Other Python processes with neither word are still ignored.
- Checks:
  - py_compile; test suite test_odoo_warmup (17 tests).
- Action required: none. Send the output of ps -o pid,uid,cmd -C python3 (or the Python line of the Odoo process) if the detection still finds no port.

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

### 2.82.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: the regex that reads the review summary of app-log-check.py expected "entrée(s)" or "erreur(s)" and no longer matched the plural words without marker. Fix: the regex accepts the plural with an optional "s".
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.
### 2.82b.20261029.212344 - Burst and shared thresholds read from apps/_seuils.py

- Title: Burst and shared thresholds read from apps/_seuils.py.
- Reason: Burst thresholds must match app-log-live.py and the shared file, so that one change applies to both programs.
- Changes:
  - BURST_PAGES and BURST_WINDOW_S now come from apps/_seuils.py through charger_seuils_communs(); the built-in values are kept without the module.
  - Warnings from the shared file are printed on stderr.
  - Files: web-monitor.py, apps/_seuils.py, nginx-tools-tests/test_seuils.py.

### 2.81.20261028.214122 - --menu: English programs translate the menu and its help through their catalogue

- Title: --menu: English programs translate the menu and its help through their catalogue.
- Reason: With --lang en, the --menu help and the menu entries were partly in French: the catalogue tests (test_i18n) and the English help test (test_web_monitor) failed.
- Changes:
  - The menu entries and the --menu help are written in English in the code; their French text is in lang/web-monitor.py.fr.po (msgid = English text, msgstr = French).
  - apps/_menu.py: menu() takes traduire (the program's translator) and langue (the program's display language). The menu labels and its messages follow the program's language, not only NGINX_TOOLS_I18N_LANGUE.
  - nginx-tools-tests/test_config_defaut.py: --menu is an action (CLI only, like --backup), excluded from the check of the configuration model.
  - Files: web-monitor.py, lang/web-monitor.py.fr.po, apps/_menu.py, nginx-tools-tests/test_config_defaut.py, CHANGELOG.md.
- Bugs fixed: symptom: test_i18n reported French text in the code of this English program. Diagnosis: the new menu strings were French in the code, but this program's code is English and its texts are translated through lang/. Correction: English strings plus catalogue entries.
- Safeguards and edge cases: the menu labels, its confirmation and cancel messages follow the language of the program; the entries still run the same options as before.
- Checks: test_i18n (catalogues), test_menu, test_config_defaut, the English help test of this program where it exists.
- Action required: none.

### 2.80.20261028.211449 - --menu: interactive menu of the usual operations

- Title: New option --menu: a menu (dialog when installed, text otherwise) for the usual operations of web-monitor.py.
- Reason: Operations were only reachable through command-line options. The menu offers them by number, shows the configuration read, and asks for confirmation before operations that change the system.
- Changes:
  - New option --menu (terminal required). Entries: surveillance, sommaire, état, connexions, comptes suspects, essai, timer (installation et retrait); configuration read (c or the menu item); change log (--changelog); quit.
  - Each entry runs this program again with the options received on the command line (except --menu) plus its own option. Entries that change the system ask for confirmation first.
  - Shared library apps/_menu.py (new): dialog when installed, text menu otherwise, with a note to install dialog.
  - Help: --menu listed in alphabetical order. --help, --version and --changelog keep their priority over --menu.
  - Files: web-monitor.py, apps/_menu.py (new), nginx-tools-tests/test_menu.py (new), CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - Without a terminal, --menu refuses with an error and exit code 1; nothing is run.
  - The menu relaunches the program only; root checks, locks and confirmations stay those of the operation itself.
- Checks:
  - test_menu: --menu listed in the help, refused without a terminal.
  - Manual test in a pseudo-terminal (text menu and stand-in dialog) on read-only entries.
  - Other tests of the program and conventions: see the pull request.
- Action required: none. To get the graphical menu: sudo apt install dialog.

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

### 1.19.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: none.
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

### 1.18.20261028.214122 - --menu: English programs translate the menu and its help through their catalogue

- Title: --menu: English programs translate the menu and its help through their catalogue.
- Reason: With --lang en, the --menu help and the menu entries were partly in French: the catalogue tests (test_i18n) and the English help test (test_web_monitor) failed.
- Changes:
  - The menu entries and the --menu help are written in English in the code; their French text is in lang/zip-versions.py.fr.po (msgid = English text, msgstr = French).
  - apps/_menu.py: menu() takes traduire (the program's translator) and langue (the program's display language). The menu labels and its messages follow the program's language, not only NGINX_TOOLS_I18N_LANGUE.
  - nginx-tools-tests/test_config_defaut.py: --menu is an action (CLI only, like --backup), excluded from the check of the configuration model.
  - Files: zip-versions.py, lang/zip-versions.py.fr.po, apps/_menu.py, nginx-tools-tests/test_config_defaut.py, CHANGELOG.md.
- Bugs fixed: symptom: test_i18n reported French text in the code of this English program. Diagnosis: the new menu strings were French in the code, but this program's code is English and its texts are translated through lang/. Correction: English strings plus catalogue entries.
- Safeguards and edge cases: the menu labels, its confirmation and cancel messages follow the language of the program; the entries still run the same options as before.
- Checks: test_i18n (catalogues), test_menu, test_config_defaut, the English help test of this program where it exists.
- Action required: none.

### 1.17.20261028.211449 - --menu: interactive menu of the usual operations

- Title: New option --menu: a menu (dialog when installed, text otherwise) for the usual operations of zip-versions.py.
- Reason: Operations were only reachable through command-line options. The menu offers them by number, shows the configuration read, and asks for confirmation before operations that change the system.
- Changes:
  - New option --menu (terminal required). Entries: comparaison des archives, comparaison avec l'installation; configuration read (c or the menu item); change log (--changelog); quit.
  - Each entry runs this program again with the options received on the command line (except --menu) plus its own option. Entries that change the system ask for confirmation first.
  - Shared library apps/_menu.py (new): dialog when installed, text menu otherwise, with a note to install dialog.
  - Help: --menu listed in alphabetical order. --help, --version and --changelog keep their priority over --menu.
  - Files: zip-versions.py, apps/_menu.py (new), nginx-tools-tests/test_menu.py (new), CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - Without a terminal, --menu refuses with an error and exit code 1; nothing is run.
  - The menu relaunches the program only; root checks, locks and confirmations stay those of the operation itself.
- Checks:
  - test_menu: --menu listed in the help, refused without a terminal.
  - Manual test in a pseudo-terminal (text menu and stand-in dialog) on read-only entries.
  - Other tests of the program and conventions: see the pull request.
- Action required: none. To get the graphical menu: sudo apt install dialog.

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

### 1.25.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: one marker was left in the TIMER_TIME comment of the configuration template ("heure(s)", found by test_i18n): it now says "heures", as its French catalogue entry already did.
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

### 1.24.20261029.200500 - Retention on the remote copy, result of the restoration test in --status

- Title: the remote copy follows the local retention, and --status shows whether the last restoration test succeeded.
- Reason: the retention only cleaned the local folder. The remote copy (REMOTE, for example on another server through Tailscale) grew without limit until its disk was full. The restoration test (--test-restore) existed, but its result was not kept: nothing said when it last ran or whether it succeeded.
- Changes:
  - retention_distante (new, after retention): after the local retention, the remote folder of each database is made equal to the local one with rsync --delete --delete-excluded and include filters (*.zip, *.tar.xz, *.sha256 only). --max-delete MAX_REMOTE_DELETE stops the run instead of deleting more.
  - Configuration: REMOTE_RETENTION=yes|no (default yes) and MAX_REMOTE_DELETE=20 (integers checked). Both read from the configuration files; the example files document them.
  - --test-restore: the result (date and success or failure) is written to last-restore-test in the state folder (not in dry-run).
  - --status: shows the result of the last restoration test; a failure is an error, a success older than 7 days or no test at all is a warning. The remote retention setting is shown next to the remote copy.
  - Files touched: odoo-backup.sh (version 1.24), lang/odoo-backup.en.po (15 fragments), doc/en and doc/fr odoo-backup.conf.example, CHANGELOG.md.
- Bugs fixed: none, but the remote copy never being pruned was a growing risk: symptom = the remote disk fills; diagnosis = retention() only handles DEST; fix = retention_distante.
- Safeguards and edge cases:
  - No remote pruning when there is no local archive for the database: an empty local folder would empty the remote one. A warning is written instead.
  - --max-delete: at most MAX_REMOTE_DELETE files are deleted in one run; above that rsync fails and the warning says so.
  - REMOTE_RETENTION=no keeps the previous behaviour exactly.
  - The remote folder is assumed dedicated to the backups of this program: with REMOTE_RETENTION=yes, files of other kinds in it are deleted.
  - The rsync failure is recorded in last-failure (state read by --status and web-monitor.py).
- Checks:
  - bash -n OK; --version displays the dynamic version.
  - Functional check of the guard (empty local folder) with the function extracted and stubs.
  - NOT checked here: the rsync deletion itself, because rsync is not installed in the test environment. To be checked on the backup server: a remote folder with an extra old archive, run the backup once, and see it removed.
- Action required: before the first run with REMOTE_RETENTION=yes, check the remote folder content (the files not produced by odoo-backup.sh would be deleted), or set REMOTE_RETENTION=no. After installation, run odoo-backup.sh --test-restore once so that --status has a result.

### 1.23.20261028.214122 - --menu: catalogue entries for the menu and its help line (English)

- Title: --menu: catalogue entries for the menu and its help line (English).
- Reason: The catalogue test (test_i18n) reported the new --menu strings of this program as untranslated.
- Changes:
  - lang/odoo-backup.sh.en.po: entries for the menu entries (their English text is shown from the EN field of the menu, so msgstr is empty) and for the --menu help line (English translation).
  - Files: lang/odoo-backup.sh.en.po, CHANGELOG.md.
- Bugs fixed: symptom: test_i18n failure on this program. Diagnosis: the catalogue had no entries for the new strings. Correction: entries added. The program code is unchanged.
- Safeguards and edge cases: no change in behaviour; the French and English menus are unchanged.
- Checks: test_i18n (catalogues of bash programs).
- Action required: none.

### 1.22.20261028.211449 - --menu: interactive menu of the usual operations

- Title: New option --menu: a menu (dialog when installed, text otherwise) for the usual operations of odoo-backup.sh.
- Reason: Operations were only reachable through command-line options. The menu offers them by number, shows the configuration read, and asks for confirmation before operations that change the system.
- Changes:
  - New option --menu (terminal required). Entries: sauvegarde, essai (--dry-run), état, test de restauration, timer, retrait du timer; configuration read (c or the menu item); change log (--changelog); quit.
  - Each entry runs this program again with the options received on the command line (except --menu) plus its own option. Entries that change the system ask for confirmation first.
  - Shared library apps/_menu.sh (new): dialog when installed, text menu otherwise, with a note to install dialog.
  - Help: --menu listed in alphabetical order. --help, --version and --changelog keep their priority over --menu.
  - Files: odoo-backup.sh, apps/_menu.sh (new), nginx-tools-tests/test_menu.py (new), CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - Without a terminal, --menu refuses with an error and exit code 1; nothing is run.
  - The menu relaunches the program only; root checks, locks and confirmations stay those of the operation itself.
- Checks:
  - test_menu: --menu listed in the help, refused without a terminal.
  - Manual test in a pseudo-terminal (text menu and stand-in dialog) on read-only entries.
  - Other tests of the program and conventions: see the pull request.
- Action required: none. To get the graphical menu: sudo apt install dialog.

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

### 1.23.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: none.
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

### 1.22.20261028.214122 - --menu: catalogue entries for the menu and its help line (English)

- Title: --menu: catalogue entries for the menu and its help line (English).
- Reason: The catalogue test (test_i18n) reported the new --menu strings of this program as untranslated.
- Changes:
  - lang/odoo-update-module.sh.en.po: entries for the menu entries (their English text is shown from the EN field of the menu, so msgstr is empty) and for the --menu help line (English translation).
  - Files: lang/odoo-update-module.sh.en.po, CHANGELOG.md.
- Bugs fixed: symptom: test_i18n failure on this program. Diagnosis: the catalogue had no entries for the new strings. Correction: entries added. The program code is unchanged.
- Safeguards and edge cases: no change in behaviour; the French and English menus are unchanged.
- Checks: test_i18n (catalogues of bash programs).
- Action required: none.

### 1.21.20261028.211449 - --menu: interactive menu of the usual operations

- Title: New option --menu: a menu (dialog when installed, text otherwise) for the usual operations of odoo-update-module.sh.
- Reason: Operations were only reachable through command-line options. The menu offers them by number, shows the configuration read, and asks for confirmation before operations that change the system.
- Changes:
  - New option --menu (terminal required). Entries: essai (--dry-run), activité du site, mise à jour des modules; configuration read (c or the menu item); change log (--changelog); quit.
  - Each entry runs this program again with the options received on the command line (except --menu) plus its own option. Entries that change the system ask for confirmation first.
  - Shared library apps/_menu.sh (new): dialog when installed, text menu otherwise, with a note to install dialog.
  - Help: --menu listed in alphabetical order. --help, --version and --changelog keep their priority over --menu.
  - Files: odoo-update-module.sh, apps/_menu.sh (new), nginx-tools-tests/test_menu.py (new), CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - Without a terminal, --menu refuses with an error and exit code 1; nothing is run.
  - The menu relaunches the program only; root checks, locks and confirmations stay those of the operation itself.
- Checks:
  - test_menu: --menu listed in the help, refused without a terminal.
  - Manual test in a pseudo-terminal (text menu and stand-in dialog) on read-only entries.
  - Other tests of the program and conventions: see the pull request.
- Action required: none. To get the graphical menu: sudo apt install dialog.

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

### 2.69.20261031.191441 - No 404 question when the list of refused URIs does not change

- Title: the question "Refuser (404) : ... ? [o/N]" is no longer asked when the list of refused URIs does not change.
- Reason: the administrator saw "URI refusées actuellement : aucune" followed by the question for an unchanged empty list, which is confusing.
- Cause: the program compared the content of snippets/uri-desactivees.conf with the text it would generate. A missing file, or a different header, made the comparison fail, so the question was asked even when no URI was added or removed.
- Changes: section 12c (URI refusées), nginx-hardening.sh: when the list before and after is the same, the step reports it and writes nothing. The question remains for real changes (--disable-uri, --enable-uri).
- Bugs fixed: symptom: question for an unchanged list; diagnosis: comparison of the whole file instead of the list; fix: comparison of the lists first.
- Safeguards and edge cases: the file uri-desactivees.conf is still created empty by fragments_generes_assurer (step 0f) when missing, so nginx -t does not fail; a changed list still asks for confirmation (o/N), or is applied with --yes; without a terminal nothing changes, as before.
- Checks performed: bash -n on nginx-hardening.sh.
- Action required: none. The question disappears on the next --update when the list is unchanged. To refuse a path, use --disable-uri CHEMIN and confirm.

### 2.68.20261031.180855 - Odoo editor shapes: no more 429 on normal loading (nginx configuration 1.16)

- Title: the shapes of the Odoo site editor (/web_editor/shape/) use the general limit instead of the strict zone odoo_shapes.
- Reason: a logged-in administrator editing the "Partenaires" page received 331 HTTP 429 responses. The editor loads about sixty decorative shapes at once; the zone odoo_shapes allowed one request every 3 seconds per address after a burst of 10.
- Changes (files of nginx/, installed by --update):
  - nginx/snippets/odoo/_odoo-common.conf: location ~ ^/web_editor/shape/ uses limit_req zone=odoo_general burst=120 nodelay (30 requests/s, shared with the rest of the site) instead of odoo_shapes burst=10. The curl limit (odoo_curl) is kept: it only applies to the curl user agent.
  - nginx/conf.d/odoo-global.conf: comment added to the odoo_shapes zone (no longer used).
  - nginx/VERSION: 1.16.20261031.180855.
  - nginx-hardening.sh: version bumped because this program installs these files.
- Bugs fixed:
  - Symptom: 429 responses on /web_editor/shape/ for a session connected to the back office.
  - Diagnosis: error.log: "limiting requests, excess: 10.x by zone odoo_shapes" for the same address, requests about one second apart within a page load.
  - Fix: general limit instead of the strict zone for this location only.
- Safeguards and edge cases:
  - Trade-off, to decide with the administrator: the zone odoo_shapes was created against an automated enumeration of shape variants (one request every 2 to 3 seconds). That enumeration would no longer be refused by this location. The general limit (30 requests/s) still caps abuse. If the enumeration returns, a zone with rate=60r/m and burst=40 would be a middle ground (not applied in this version).
  - The routes /web/image/ and the static assets are not changed.
  - The nginx file test test_config_nginx still passes (route not refused by the security rules).
- Checks performed: test_config_nginx OK. nginx -t was not run here: this sandbox has no access to the nginx server.
- Action required: on each Odoo server (production, then development), run as root "nginx-hardening.sh --update" and approve the displayed diff. The program tests the configuration (nginx -t) and reloads nginx. Then check the error log: "grep 'odoo_shapes' /var/log/nginx/*error.log" should stop growing.

### 2.67.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: the removal of the marker also renamed two functions of the awk program that checks the websocket locations (trim(s) became trims, unquote(s) became unquotes), so the awk program raised a syntax error and every correct websocket location was reported as [FAIL]. Diagnosis: 8 tests of test_nginx_hardening failed on the websocket checks. Fix: the two function definitions and their call are restored to their original names; only the displayed texts keep the change.
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

### 2.66.20261029.205500 - Configuration model and catalogue complete for --help; changelog in version order

- Title: the options of --help are all in the configuration model, the --yes help line is translated, and the changelog is in descending version order.
- Reason: three checks of the test suite failed on this program: --test-rules and six other options were missing from doc/en/nginx-hardening.conf.example; the English catalogue did not match the --yes help line (its wording changed in 2.61); the entries of the changelog were not in descending order for versions 2.61 to 2.63.
- Changes:
  - doc/en/nginx-hardening.conf.example: a block lists --backup, --disable-uri, --enable-uri, --menu, --rollback, --test-rules and --yes, as comments (no active line).
  - lang/nginx-hardening.en.po: the msgid of the --yes help line is the text the program prints; the msgstr says the option applies to --rollback, --disable-uri and --enable-uri.
  - CHANGELOG.md: the blocks of the nginx-hardening section are sorted by version, descending (the newest first).
  - Files touched: nginx-hardening.sh (version 2.66), CHANGELOG.md, lang/nginx-hardening.en.po, doc/en/nginx-hardening.conf.example.
- Bugs fixed:
  - Symptom: test_config_defaut and test_i18n failed for nginx-hardening.sh, test_conventions for its changelog. Diagnosis: the tests read the configuration example and the catalogue, not only the program. Fix: as above.
- Safeguards and edge cases:
  - Program behaviour unchanged: only the example, the catalogue and the changelog order changed.
  - Each changelog block keeps its own text; only the order of the blocks changed.
- Checks:
  - bash -n OK; --version displays the dynamic version; --help unchanged.
  - Test suite: see the verdict of the testeur agent in the pull request.
- Action required: none.

### 2.65.20261029.084500 - --test-rules: read-only curl checks of the nginx rules

- Title: New option --test-rules sends a series of curl requests to the local nginx and reports whether each rule still refuses or serves what it should.
- Reason: After --update, Martial wants to verify in one command that the nginx rules are in place and still working (no manual curl series). Asked during the work on the tags filter.
- Changes:
  - New option --test-rules (help in alphabetical order, in colour as the others). Function tester_regles; the dispatch comes after the helper functions and before any step, so nothing is installed or modified.
  - For each server_name read from nginx -T (same reading as step 10): 8 requests, sent to 127.0.0.1:443 with --resolve, so the DNS and the external firewall do not matter. Cases: tags malformed refused (404, rule 3 bis), legitimate tags accepted, hidden file refused (404, rule 4), encoded directory traversal refused (404, rule 3), TRACE refused (405, rule 2), unwanted robot refused (403, bot_blocker), home page served, robots.txt served (200).
  - Verdict: one line per case [OK] or [FAIL] with the code obtained and the code expected; summary line; exit code 0 if all cases pass, 1 otherwise. For an application other than Odoo, the step is not applicable (sans_objet), exit 0.
  - Files: nginx-hardening.sh, lang/nginx-hardening.en.po (English entries), nginx-tools-tests/test_test_rules.py (new: stubs nginx and curl, checks exit codes and messages), CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - Read-only: no file is written, no reload, no package installed. The dispatch runs before the package checks.
  - nginx or curl missing: refusal with exit 1, nothing else run.
  - No server_name testable: exit 1 with a message.
  - Requests use -g (no curl globbing, so [35,+40] is sent as is) and a timeout of 8 s; a failed connection gives code 000, which counts as a failure.
  - A 2xx or 3xx answer counts as "not blocked" for the cases marked as legitimate.
  - The sentinel 2xx3xx and the catalogue entries keep the English output readable.
- Checks performed:
  - test_test_rules (2 tests, stubs): all rules in place -> exit 0 with 8 cases OK; one rule missing -> exit 1 with [FAIL].
  - Manual run with stubs: 8 OK, 0 failed; with a server answering 200 everywhere: 5 failed, exit 1.
  - test_i18n (catalogues, English entries), test_nginx_hardening, test_docs, test_nginx_uri, test_menu: OK.
  - Not verified here: a real nginx and real Odoo; the requests were only run against stubs.
- Action required: none for the program. On PROD and DEV, after --update, run: nginx-hardening.sh --app=odoo --test-rules

### 2.64.20261029.081857 - Malformed tags parameter on event pages refused (404) by the generic nginx configuration 1.15

- Title: The generic nginx configuration refuses a ?tags= value that is not a list of numbers on the event pages.
- Reason: Odoo's event search reads the tags parameter with literal_eval. A source sent about 2 200 requests with invented tags values (tags=stfD, search values full of quotes and brackets) on /en_CA/event and /es/event. Each request with a value such as stfD ended as an unhandled ValueError (HTTP 500 and an ERROR odoo.http line). Martial asked for a filter in the nginx configuration.
- Changes:
  - nginx/snippets/securite-commune.conf, new rule 3 bis: a request whose path is /event (any language prefix) and whose query string contains tags= followed by a value other than [numbers, commas, plus] (with %2B, %2C or %20 allowed) gets 404, as the rule for hidden files does. Legitimate links of the site, such as tags=[35,+40,+12,+37], pass.
  - nginx/VERSION: 1.15.20261029.081857 (configuration archive).
  - doc/nginx-tools.version: 1.155.20261029.081857 (archive of the tools).
  - nginx-hardening.sh: SCRIPT_VERSION only.
  - nginx-tools-tests/test_nginx_uri.py: class FiltreTagsEvenements (malformed values refused, site links accepted), reads the rule from securite-commune.conf.
  - Files: nginx/snippets/securite-commune.conf, nginx/VERSION, doc/nginx-tools.version, nginx-hardening.sh, nginx-tools-tests/test_nginx_uri.py, CHANGELOG.md.
- Bugs fixed:
  - Symptom: 11 HTTP 500 responses and 11 ERROR odoo.http lines in 10 minutes, all on /en_CA/event with a tags value that is not a list.
  - Diagnosis: website_event/models/event_event.py, _search_get_detail: literal_eval(tags) receives a bare name (stfD). The exception is not caught, so the request fails with 500. No data is exposed: the error happens before the database query.
  - Correction: the request is refused by nginx before it reaches Odoo.
- Safeguards and edge cases:
  - The rule runs on the whole query string, so a valid tags= followed by an invalid one (tags=[35]&tags=stfD) is refused.
  - Encoded brackets (%5B35%5D) are refused too: the site writes literal brackets. If a partner link is encoded, it will get 404 and must be rewritten with literal brackets.
  - The regex has no backslash escaping inside the double quotes beyond the characters used elsewhere in the file; nginx -t has not been run here (nginx is not installed in the test environment).
- Checks:
  - python unittest nginx-tools-tests/test_nginx_uri.py: 7 tests OK (5 existing, 2 new). The regex was also checked against 16 sample URIs.
  - Not verified here: nginx -t on a real server, and the 500 count after deployment.
- Action required: on each server (PROD Odoo, DEV Odoo), run nginx-hardening.sh --update. It runs nginx -t and reloads nginx itself (nginx_appliquer) when the configuration is valid; it does not test the site afterwards for this rule, so check by hand that a request with tags=stfD returns 404 and that /es/event/jornada-linux-2025-23/track?tags=[35,+40] still returns 200. Not done here: auto-ban in web-monitor.py (the recommendations file is 69 h old, the timer should be checked).

### 2.63.20261028.222437 - Catalogue entries for the bash messages not yet translated (rollback, URI, backup, menu)

- Title: English catalogue entries for the bash messages that were still French (backup, rollback, refused URIs, configuration reading, menu).
- Reason: The catalogue test (test_i18n) reported about 90 French messages without an English entry.
- Changes:
  - lang/nginx-hardening.en.po: entries for the messages and help lines listed by the test. The program code is unchanged.
  - Files: lang/nginx-hardening.en.po, CHANGELOG.md.
- Bugs fixed: symptom: with --lang en, these messages stayed in French. Diagnosis: the catalogue had no entries for messages added since it was written. Correction: entries added.
- Safeguards and edge cases: the answers o/y and the words expected by the program are unchanged; the English prompt still accepts y.
- Checks: test_i18n (catalogues of the bash programs), test_odoo_conf (English output without French).
- Action required: none.

### 2.63.20261028.190500 - A reload refused by nginx is reported as a failure

- Title: After a reload, the error log is read: a new [emerg] line means nginx refused the new configuration and kept the old one.
- Reason: On the server, nginx refused every reload since 11:11 (limit_req zone odoo_general: key changed from $limit_key_general to $limit_key_general_std), yet systemd reported "Reloaded" and the script announced "nginx rechargé". The rules of the last updates were never active.
- Detail: nginx_appliquer keeps the reload exit code, waits NGINX_HARDENING_RELOAD_WAIT seconds (1 by default), compares the number of [emerg] lines in NGINX_HARDENING_ERROR_LOG (default /var/log/nginx/error.log) before and after, and prints the last [emerg] line. Callers already print "nginx n'a pas pu être rechargé" on failure, and the previous files are restored when nginx -t refuses.
- Files: nginx-hardening.sh, CHANGELOG.md.
- Checks: stub systemctl: reload without error reports success; reload that adds an [emerg] line reports the refusal. ShellCheck 0.11.0: clean.
- Cause to fix on the server (not done by this version): a zone whose key changed needs a restart, or a new zone name so that a reload is accepted. Action required: decide between a short restart (sudo nginx -t then sudo systemctl restart nginx) and a renamed zone in the repository.

### 2.62.20261028.210125 - --menu: graphical menu with dialog, text menu as fallback

- Title: The menu of --menu uses dialog when it is installed; without dialog, the text menu is still shown, with a note.
- Reason: The menu was only a text menu. Martial expects the dialog menu, as in odoo-sql-maint.
- Changes:
  - With dialog installed and a terminal available, --menu opens a dialog window: 1 check, 2 apply (confirmation in a dialog yes/no box), 3 rollback, 4 default options read from the configuration files (in a text box), 5 change log, Quit.
  - Operations that print output (1, 2, 3, 5) leave dialog, run in the terminal (their questions still work), then wait for Enter before returning to the window.
  - Without dialog (or without a terminal for it), the text menu of 2.61 is used and a note says: sudo apt install dialog.
  - The menu actions are in one function (menu_action) shared by both modes, so root and confirmation checks are not duplicated.
  - dialog answers are read from a file (--output-fd), as in odoo-sql-maint; the call is protected so that set -e does not stop the program when dialog is cancelled.
  - Functions: dialog_run, menu_dialog, menu_texte, menu_config_fenetre, menu_action, menu_principal (dispatch).
  - Help and header: --menu now says dialog when installed.
  - Files: nginx-hardening.sh, CHANGELOG.md.
- Bugs fixed:
  - Symptom: with dialog expected, --menu showed only the text menu.
  - Diagnosis: the 2.61 menu never called dialog.
  - Correction: dialog is used when available (see above).
- Safeguards and edge cases:
  - Without a terminal, --menu still refuses (code 1).
  - --update and --rollback still refuse without root, before any question; a declined confirmation changes nothing.
  - The menu runs before the lock and before any change, as in 2.61.
- Checks:
  - Test with a stand-in dialog command (records calls, returns scripted answers): option 4 opens the text box, option 1 runs the check and returns to the window, option 2 with a declined confirmation changes nothing, q quits.
  - Text menu (dialog absent from PATH): note shown, unknown choice handled, q quits.
  - Without a terminal: refused with code 1.
  - The real dialog rendering was NOT tested in this session (dialog could not be installed here); to be checked on a real terminal.
  - The accepted confirmation of --update was NOT run here (root on the test machine would have changed nginx and the firewall).
- Action required: install dialog on the servers to get the graphical menu (sudo apt install dialog). Then sudo nginx-hardening.sh --menu.

### 2.62.20261028.181500 - --update checks over HTTP that refused paths answer 404

- Title: After a change of refused paths, --update requests each refused path on every public name (and under /es) and reports any answer other than 404.
- Reason: 2.61 reported "nginx rechargé" as success without checking the result. On the server, https://www.rencontres-linux.quebec/shop still answered 200 after the reload.
- Detail: New functions uri_noms_testables (public names from nginx -T, same rules as the HSTS step) and uri_verifier (curl --resolve to 127.0.0.1, read-only GET). The check runs only with --update, after the file is written or was already up to date. It reports each test that does not answer 404 and prints the next command to run. No automatic restore: nginx -t already accepted the configuration, so the cause is a server block that does not apply the rule.
- Files: nginx-hardening.sh, CHANGELOG.md, nginx-tools-tests/test_nginx_uri.py.
- Checks: test_nginx_uri (8 tests: 404 on every name, 200 reported as a failure, and the earlier cases). ShellCheck 0.11.0: clean.
- Action required: run sudo nginx-hardening.sh --update (the verification runs). If it reports a failure, send the lines it prints.

### 2.61.20261028.203623 - --menu: interactive menu for the usual operations

- Title: New option --menu: a text menu for the usual operations, so the options no longer have to be remembered.
- Reason: The operations (check, update, rollback, change log) and the reading of the configuration files were only reachable through command-line options. The menu offers them with a number, and shows the default options read from the configuration files.
- Changes:
  - New option --menu (terminal required). Menu: 1 check (--check), 2 apply the changes (--update, root and confirmation required), 3 restore the latest backup (--rollback, root, confirmation asked by the operation), 4 show the default options read from the configuration files, 5 show the change log (--changelog), q quit.
  - Option 4 lists the configuration files read (in order, the last one wins, with their modification date) and each default option they provide (for example --odoo-http-port 8169), with the invalid or French values reported.
  - Each choice runs this program again with the same command-line options (except --menu) plus the chosen operation, so the menu and the options share one code path. The program's exit code is shown after each operation, and the menu stays open.
  - Functions: menu_principal, menu_lancer, menu_config_voir, menu_confirmer. Variables: MENU, ARGS_INITIAUX (the options received, kept before the parsing loop).
  - Help: --menu listed in alphabetical order, between --mail-user and --odoo-conf. The usage line and the description in the header are updated.
  - Files: nginx-hardening.sh, CHANGELOG.md, nginx-tools-tests/test_nginx_hardening.py (one test added).
- Bugs fixed: none.
- Safeguards and edge cases:
  - Without a terminal (input or output redirected, cron, pipe), --menu refuses with an error and exit code 1; nothing is run.
  - The menu runs before the lock and before any change: the operations it starts keep their own safeguards (root check, lock, backup before --update, confirmation before --update and --rollback).
  - --update from the menu is refused with a clear message when the program is not run as root, before asking for confirmation.
  - Nothing is added to the configuration model: --menu is an action, and actions stay on the command line only (like --rollback and --update).
- Checks:
  - test_nginx_hardening: new test test_menu_sans_terminal_refuse_et_l_aide_le_liste (refusal without a terminal, --menu in the help).
  - Manual test in a pseudo-terminal, with a temporary configuration folder: menu displayed, option 4 lists the files read and the options, unknown choice handled, option 1 started and its exit code shown, q quits.
  - test_conventions (version format, change log order, alphabetical options in the help): run.
  - Known failure before this change, not caused by it: test_config_defaut (options missing from doc/en/nginx-hardening.conf.example: --backup, --disable-uri, --enable-uri, --rollback, --yes; actions, not settings). Same for nginx-log-audit.sh, app-log-live.py and odoo-warmup.py.
- Action required: none. Try it with: sudo nginx-hardening.sh --menu

### 2.61.20261028.180500 - --disable-uri / --enable-uri: confirmation and list of refused paths

- Title: Changing the refused paths asks for confirmation, after showing the paths refused now and after the change.
- Reason: 2.60 applied the refusal of /shop during --update without any question, and nothing showed the list of refused paths.
- Detail: Step 12c prints "URI refusées actuellement" and the list after the change. With a terminal: question [o/N], default no. Without a terminal: nothing is changed unless --yes is given (--yes is shared with --rollback). --check shows the pending change. Same rule as before: nginx -t before the reload, previous file restored on refusal.
- Files: nginx-hardening.sh, CHANGELOG.md, nginx-tools-tests/test_nginx_uri.py.
- Checks: test_nginx_uri (6 tests, including: no terminal and no --yes = nothing changed); with a pseudo terminal: answer n changes nothing, answer o writes the file and reloads (stub nginx). ShellCheck 0.11.0: clean.
- Action required: to check the current refusal: grep location /etc/nginx/snippets/uri-desactivees.conf. To undo: --enable-uri /shop --update (asks first).
### 2.60.20261028.170500 - --disable-uri and --enable-uri: refuse a path of the Odoo site

- Title: Refuse (404) a path of the Odoo site in every language, for example /shop, with --disable-uri; --enable-uri removes the refusal.
- Reason: The shop attacks reached Odoo (HTTP 200) through /shop?order=. Until the vulnerability is confirmed fixed, the module's path can be refused in nginx. This is a temporary measure, not a fix.
- Detail: Option --disable-uri CHEMIN and --enable-uri CHEMIN (repeatable). The paths are validated (start with /, letters, digits, _ . / -; not "/" alone, no ".."). Step 12c writes snippets/uri-desactivees.conf: one location per path, regex (^(/[A-Za-z0-9_-]+)?PATH(/|$)) so /shop, /es/shop and /en_CA/shop are all refused. The list is kept in that file (lines "# uri : PATH"), so a later --update without the option keeps the refusals. nginx -t runs before the reload; on refusal the previous file is restored.
- Files: nginx-hardening.sh, nginx/snippets/securite-commune.conf (new include, first line of the rules), CHANGELOG.md, nginx-tools-tests/test_nginx_uri.py (new).
- Guards and edge cases: the placeholder uri-desactivees.conf is created empty before any nginx -t (fragments_generes_assurer), so an update never fails on the missing include. /shopping is not refused (the path must be followed by / or the end).
- Checks: test_nginx_uri (5 tests: addition, escaped dot, removal, retention without option, empty list, include present). ShellCheck 0.11.0: clean.
- Action required: run sudo nginx-hardening.sh --disable-uri /shop --check, then --update. To undo: --enable-uri /shop --update.

### 2.59.20261028.112400 - Backup before each --update, and --rollback to restore it

- Title: Automatic backup before every --update; --rollback restores a backup after confirmation.
- Reason: --update changes the nginx and fail2ban configuration (generic files, jails, logpath). A change that breaks nginx or fail2ban had no simple way back.
- Changes:
  - Backup before every --update (not with --check): archive of /etc/nginx and /etc/fail2ban in /var/backups/nginx-hardening/archives/AAAAMMJJ-HHMMSS-MMM-update.tar.gz, with a .txt file (version, date, folders). The BACKUP_KEEP most recent archives are kept (default 20). If the archive cannot be made, nothing is changed.
  - New option --rollback: restores the most recent archive, or --backup NAME. Shows the differences (30 first lines), asks for confirmation (--yes to skip). Before restoring, the current state is saved (avant-rollback archive).
  - Restore: the folders are moved aside, copied back, nginx -t is run; if it refuses, the folders are put back and nothing stays changed. Then nginx and fail2ban are reloaded.
  - New option --backup NAME (with --rollback) and --yes (with --rollback).
  - Environment variables (no configuration key): NGINX_HARDENING_ARCHIVE_DIR (archives, default /var/backups/nginx-hardening/archives, separate from the per-file .bak copies), NGINX_HARDENING_BACKUP_KEEP, NGINX_HARDENING_BACKUP_ROOTS (space-separated folders).
  - Files: nginx-hardening.sh, nginx-tools-tests/test_nginx_backup.py (new).
- Bugs fixed: none.
- Safeguards and edge cases:
  - Not restored by --rollback: iptables rules, installed packages, odoo.conf (never changed by this program), the /etc/default/nginx-tools-*.conf files.
  - Restoring replaces the whole folder: files added after the backup are removed. The safety archive is made first, so this can be undone.
  - Without a terminal and without --yes, nothing is restored.
- Checks:
  - test_nginx_backup (3 tests): archive contents and pruning to the newest, restore of content and removal of new files, undo when nginx -t refuses.
  - --rollback on the script: lists the archive, shows the differences, refuses without a terminal.
  - test_nginx_hardening (44) and test_conventions: see the pull request.
  - ShellCheck: no warning.
- Action required: none before the next --update (a backup is made automatically). To go back: sudo nginx-hardening.sh --rollback.

### 2.58.20261028.110200 - Jail nginx-sqli also reads blocked-probes.log (step 9b, asked before any change)

- Title: nginx-hardening.sh --update adds /var/log/nginx/blocked-probes.log to the logpath of the jail nginx-sqli, after confirmation.
- Reason: The refusals of nginx's security rules are written to blocked-probes.log. The jail nginx-sqli (defined by hand in /etc/fail2ban/jail.local on the Odoo servers) read only the access logs, so injection attempts refused by nginx were never counted. On 2026-10-28 they were banned only by nginx-blocked-probes.
- Changes:
  - New step 9b: finds the file that defines the jail (jail.local, jail.d/*.conf, jail.conf), checks whether its logpath already reads the log, and otherwise shows the difference (diff -u, 20 lines).
  - With --check: the change is reported as pending. With --update in a terminal: confirmation asked; without terminal: nothing changes.
  - On confirmation: dated backup (jail file .before-logpath-AAAAMMJJ-HHMMSS), change written with the owner and mode kept, fail2ban reloaded, then the jail's file list checked. If fail2ban does not take the change, the backup is restored and fail2ban reloaded.
  - The jail is NOT copied from the repository: its filter is the server's own and is left untouched.
  - Only Odoo (APP_NAME odoo). Other applications: nothing.
  - Helper functions: f2b_jail_fichier, f2b_section_contient, f2b_logpath_ajouter.
  - Files: nginx-hardening.sh, nginx-tools-tests/test_nginx_logpath.py (new).
- Bugs fixed: a bug found during the tests before release: the awk variable "log" is a reserved word in awk (the insertion failed). Renamed "journal".
- Safeguards and edge cases:
  - Already present: nothing is changed (checked on the jail section only, not on other sections).
  - Multi-line logpath: the new path goes after the first line; continuation lines are kept.
  - Missing section, or no logpath line in it: nothing is changed; a warning asks for a manual edit.
  - blocked-probes.log absent: warning only (nginx creates it at the first refusal).
- Checks:
  - test_nginx_logpath (4 tests): detection, insertion after the first logpath line, other sections untouched, multi-line logpath, missing section.
  - test_nginx_hardening (44 tests) OK.
  - ShellCheck: same warnings as before this change (none).
- Action required: sudo nginx-hardening.sh --check (to see the difference), then sudo nginx-hardening.sh --update and answer o to apply.

### 2.57.20261027.203437 - Generic nginx configuration 1.14: curl burst of 10, WordPress probes

- Title: generic nginx configuration 1.14 (version 1.13 of the administrator, merged into the repository's nginx/ folder).
- Reason: the administrator's 1.13 changes a human typing a few curl commands should not be refused: the curl rate stays 12 requests per minute, but a burst of up to 10 requests is accepted. The WordPress probe location also has to refuse "wp", "wp-..." and "wordpress" paths, with or without a language prefix.
- Changes:
  - nginx/conf.d/odoo-global.conf, nginx/snippets/securite-commune.conf, nginx/snippets/odoo/_odoo-common.conf: odoo_curl burst is 10 (was 0), in the server rule and in the three locations that declare their own limit_req.
  - nginx/snippets/securite-commune.conf: WordPress probe location extended with wp(?:-[a-z]+)?(?:/|$) and wordpress(?:/|$).
  - nginx/conf.d/bot_blocker.conf: comment only.
  - nginx/VERSION: 1.14; nginx/README.md: short history.
  - rlq-nginx-config.1.14.zip (site package): VERSION and README version line updated; no other change.
  - nginx-tools-tests/test_config_nginx.py: curl burst assertions updated to 10; new test test_sondes_wordpress_wp_et_wordpress_refusees.
  - Files touched: nginx/ (4 files, patched from the 1.13 tree), nginx-tools-tests/test_config_nginx.py, nginx-hardening.sh (SCRIPT_VERSION), CHANGELOG.md, run-all.sh, doc/nginx-tools.version.
- Bugs fixed: none in the program; configuration behaviour follows the administrator's decision.
- Safeguards and edge cases:
  - burst=10 with rate=12r/m: a single curl every 5 seconds or more is never refused; the 11th request in a burst is refused (429). Localhost and trusted addresses stay exempt.
  - The WordPress regex is anchored at the end (/ or end of path), so wpxyz and wordpress-like names other than the listed forms are not matched by the new alternatives.
- Checks: test_config_nginx on the merged tree (nginx/ + site package): 33 tests, OK, 2 skipped; nginx -t not run (nginx not installed here).
- Action required: after unpacking the site package and running nginx-hardening.sh --update, confirm the 0f changes (the 1.13 values replace the 1.12 values in /etc/nginx), then nginx -t and reload.

### 2.56.20261027.171700 - Generic nginx and fail2ban configuration installed by --update; site files separated

- Title: the generic nginx and fail2ban configuration lives in the repository (nginx/) and is installed by --update; the files that belong to one site (domains, vhosts, instance names, certificates) are in a separate package, rlq-nginx-config.14.zip.
- Reason: the bot blocker, the rate limits, the common security rules and the fail2ban filters are useful to any site served by nginx (Odoo, BigBlueButton), so they must be public and installed automatically, with the latest version. The site package must not contain domain names that belong to the repository. Also: a visitor who only requested browser icons (apple-touch-icon, favicon.ico) on an old host name was banned for 24 hours by the jail nginx-catchall, because its filter had no ignoreregex.
- Changes:
  - New step 0f, "Configuration nginx generique": copies nginx/ (repository, next to this script) to /etc/nginx/ with the same layout as the site package. The set depends on the detected application (APP_NAME, from apps/_profile.sh): odoo = bot blocker, odoo-global, securite-commune, _odoo-common, hsts, fail2ban filters and jails of nginx-catchall, nginx-blocked-probes and odoo-auth; bbb = bot blocker only (BigBlueButton's own rules stay with durcir_bbb).
  - Per file: identical = nothing; missing = created; different (edited by hand, or an older version) = a dated backup `NAME.before-generic-AAAAMMJJ-HHMMSS` is kept, the first 25 lines of the diff are shown, then the replacement.
  - The snippets/robots-disallow.conf file (site-specific, included by the robots map of odoo-global.conf) is created empty only if it is missing; the site package fills it.
  - Confirmation is asked in a terminal ("[o/N]"). Without a terminal nothing changes and the step says so. --check only shows the plan.
  - After the copy, fragments_generes_assurer() and nginx -t run; if nginx -t refuses, every file changed by the step is restored (backup moved back, created files removed); otherwise nginx is reloaded (nginx_appliquer).
  - nginx/ (new, repository): conf.d/bot_blocker.conf, conf.d/odoo-global.conf (the robots map now includes the site file), snippets/securite-commune.conf, snippets/odoo/_odoo-common.conf, snippets/odoo/hsts.conf, fail2ban/ (nginx-catchall, nginx-blocked-probes, odoo-auth), VERSION (1.14), README.md. Site names are replaced by a placeholder in the comments.
  - fail2ban/nginx-catchall.filter.conf: ignoreregex ignores GET/HEAD of /apple-touch-icon* and /favicon.ico on the catch-all sensor. The jail still bans scanners (raw IP, unknown host names).
  - rlq-nginx-config.14.zip (site package, separate): sites-available/, maintenance/index.html, snippets/odoo/ (env-*, name, ssl, instance files), snippets/robots-disallow.conf, README.md, VERSION (1.14).
  - nginx-tools-tests/test_nginx_hardening.py: five new tests (plan in --check without writing, identical files, modified file, no terminal, confirmation with rollback when nginx -t refuses, confirmation with a kept backup when nginx -t passes).
  - Backup suffix in English (.before-generic-), per the naming convention.
  - Files touched: nginx-hardening.sh, nginx/ (new), CHANGELOG.md, lang/nginx-hardening.en.po, nginx-tools-tests/test_nginx_hardening.py, nginx-tools-tests/test_config_nginx.py, nginx-tools-tests/run-all.sh (SCRIPT_VERSION), doc/nginx-tools.version.
- Bugs fixed:
  - Symptom: a visitor requesting only browser icons from an old host name was banned for 24 hours (nginx-catchall, 10 hits in 60 s).
  - Diagnosis: the filter counted every 444 line of the catch-all log; ignoreregex was empty.
  - Fix: ignoreregex in the filter (the audit's counterpart was fixed in 2.52).
- Safeguards and edge cases:
  - Nothing changes without a confirmation in a terminal; --check changes nothing (test: the directory stays empty).
  - A file edited by hand is never overwritten silently: the backup and the diff come first.
  - A site file that already exists (robots-disallow.conf, team and shared fragments) is never replaced by this step.
  - nginx -t is the final gate; a refusal restores the previous state, and the test covers that path.
  - Not handled yet: a generic file that the site package also contains (should not happen with the split above); BigBlueButton is limited to the bot map.
- Checks:
  - test_nginx_hardening: the five new tests pass; the rest of the module is unchanged.
  - test_config_nginx run on the merged tree (nginx/ + rlq-nginx-config.14): 32 tests OK, 2 skipped.
  - ShellCheck 0.11.0 on nginx-hardening.sh: clean.
  - Not run: nginx -t on a real server; nginx is not installed in the sandbox.
  - The odoo-warmup i18n failure is pre-existing on main and unrelated.
- Action required:
  - On the server: unpack rlq-nginx-config.14.zip into the site configuration (sites-available, snippets/odoo, maintenance, snippets/robots-disallow.conf) or keep the current files and let --update compare them.
  - Run nginx-hardening.sh --update from the repository; confirm the 0f changes (review the diff first); it runs nginx -t and reloads nginx.
  - Reload fail2ban after the install so that the nginx-catchall filter with ignoreregex applies.

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

### 2.66.20261031.193551 - No "Broken pipe" message; verification command uses zgrep

- Title: the investigation output no longer shows "sort: write failed: Broken pipe", and the suggested command reads the compressed logs too.
- Reason: during --investigate, the message "sort: write failed: 'standard output': Broken pipe" appeared in the report. The suggested command was a grep, which does not read the .gz rotations, although the explanation said so.
- Cause: "head" closed its input before "sort" had finished writing (in the lists of URLs and User-Agents, and in the top URL), so sort received SIGPIPE.
- Changes:
  - investigate_and_propose: "head -n" and "head -1" replaced by awk, which reads all its input (same output).
  - investigate_and_propose: the verification command is now zgrep -F "IP " PATH | awk ... | sort | uniq -c, with the path without the "(zgrep pour les .gz)" suffix.
- Bugs fixed: symptom: Broken pipe message; diagnosis: head closes the pipe early; fix: awk.
- Safeguards and edge cases: zgrep also reads uncompressed files; the output lists are unchanged; the path is cut at the first "  (" so callers without the suffix are unaffected.
- Checks performed: bash -n; unit tests of nginx-log-audit and i18n (see the commit).
- Action required: none.

### 2.65.20261031.180855 - 429 separated from hostility; Odoo accounts identified in --investigate

- Title: a 429 (nginx rate limiting) is no longer counted as an error of hostility; --investigate shows which nginx zone refused the address and which Odoo accounts were active during its requests.
- Reason: the address 174.94.93.49 was scored with its 331 HTTP 429 responses, although it was a logged-in back-office session (the Odoo editor loading shapes, page "Partenaires"). The program could not say which rule had produced the 429. The administrator also asked to identify the Odoo user from the database.
- Changes:
  - investigate_and_propose: the number of 429 is read from the HTTP codes; the "error rate" criterion of the score uses the errors without the 429 (line "hors 429"); a [i] line shows the 429 count and the zones read from error.log.
  - New function limites_debit_ip IP: counts the "limiting requests" lines of the address per nginx zone, in error.log and its rotations (.gz included).
  - New function comptes_bd_ip IP (only with --investigate): sends the request times of the address to apps/_odoo_db.py --correlate and lists the Odoo accounts active within 2 hours of them.
  - --investigate help text: one line added (lang/nginx-log-audit.en.po updated, all new messages translated).
- Bugs fixed:
  - Symptom: the report gave "Taux d'erreurs : 331/1116" and a session identified as a human was reported without an account.
  - Diagnosis: the 429 were in the error count; the error log showed "limiting requests" in zone odoo_shapes for this address; the journal of Odoo did not contain a login for this address in 100 days.
  - Fix: separation of the 429, zone display, and database correlation.
- Safeguards and edge cases:
  - A 429 alone never adds to the hostility signs; the score is computed on the other signs.
  - The database is read only (default_transaction_read_only forced by PostgreSQL, see apps/_odoo_db.py). Without root, the program prints a message and continues.
  - Odoo does not store the IP address of its sessions: the account list is a lead based on the time (margin of 2 hours), never a proof. The message says so.
  - If a table is missing in the Odoo version (bus_presence), that source is skipped.
- Checks performed: bash -n on the script; test_i18n and test_nginx_log_audit OK; --version shows the new version; the correlation command returns the expected message without root. Full suite (run-all.sh): the remaining failures are in other programs (ruff on nginx-tools-tests/test_menu.py and web-monitor.py, app-log-live tests and models, odoo-warmup and web-monitor changelog order, odoo-backup model); none in the files changed here.
- Action required: as root on the production server, run "nginx-log-audit.sh --investigate 174.94.93.49" to see the accounts found in the database. Then apply the nginx fix described in the nginx-hardening.sh 2.68 entry.

### 2.64.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: none.
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

### 2.63.20261029.210000 - --compare: the last 24 hours against the 24 hours before, written to a file

- Title: a read-only comparison report, written to a file with mode 600, to see whether the traffic, the blocked requests or the errors grow compared with the day before.
- Reason: the reports of this program describe what happened, not what changed. The administrator wants the comparison now, and sending it by e-mail later.
- Changes:
  - New option --compare [FILE] (help line in the list of options). Without FILE, the report goes to compare-ENV-YYYYmmdd-HHMMSS.txt in the state folder.
  - compare_report: reads the access log through filter_last_hours (48 hours), leaves out our own programs (filtrer_nos_programmes), and counts two windows: the last 24 hours and the 24 hours before. Blocked = 403, 404, 405, 429, 444 (the list of --stats). Writes the total, the 4xx and 5xx errors, the blocked requests, the distinct addresses, the 10 most blocked paths and the 10 most blocked addresses, each with its count in the 24 hours before.
  - Dispatch: right before the main report; --compare exits after writing the file. No lock is taken for it (read-only), like --stats.
  - Files touched: nginx-log-audit.sh (version 2.63), nginx-tools-tests/test_nginx_log_audit.py (test_263_compare_24_heures_contre_24_precedentes), CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - The file and its temporary files are created with umask 077; the final file is mode 600 (it contains addresses).
  - Writes go to a temporary file then move: an interrupted run leaves no half-written report.
  - Lines outside the 48 hours are ignored; lines without a readable date are skipped.
  - The windows are sliding: the 24 hours before are the 24 hours ending 24 hours ago, not a fixed reference.
  - Times are read in the local time of the server, as the filter --last does: a log written in another time zone shifts the windows.
- Checks:
  - bash -n OK; --version displays the dynamic version.
  - Unit test test_263_compare_24_heures_contre_24_precedentes (see the verdict of the testeur agent in the pull request).
- Action required: none. Nothing is sent by e-mail in this version; the file can be sent later with the existing mail tools.

### 2.62.20261028.214122 - --menu: catalogue entries for the menu and its help line (English)

- Title: --menu: catalogue entries for the menu and its help line (English).
- Reason: The catalogue test (test_i18n) reported the new --menu strings of this program as untranslated.
- Changes:
  - lang/nginx-log-audit.sh.en.po: entries for the menu entries (their English text is shown from the EN field of the menu, so msgstr is empty) and for the --menu help line (English translation).
  - Files: lang/nginx-log-audit.sh.en.po, CHANGELOG.md.
- Bugs fixed: symptom: test_i18n failure on this program. Diagnosis: the catalogue had no entries for the new strings. Correction: entries added. The program code is unchanged.
- Safeguards and edge cases: no change in behaviour; the French and English menus are unchanged.
- Checks: test_i18n (catalogues of bash programs).
- Action required: none.

### 2.61.20261028.222437 - Catalogue entries for the --ban-sqli messages (English)

- Title: English catalogue entries for the --ban-sqli messages.
- Reason: The catalogue test (test_i18n) reported the --ban-sqli messages, added without catalogue entries.
- Changes:
  - lang/nginx-log-audit.en.po: entries for the messages and the help line of --ban-sqli. The program code is unchanged.
  - Files: lang/nginx-log-audit.en.po, CHANGELOG.md.
- Bugs fixed: symptom: with --lang en, the --ban-sqli messages stayed in French. Diagnosis: no catalogue entries. Correction: entries added.
- Safeguards and edge cases: no change in behaviour.
- Checks: test_i18n (catalogues of the bash programs).
- Action required: none.

### 2.61.20261028.211449 - --menu: interactive menu of the usual operations

- Title: New option --menu: a menu (dialog when installed, text otherwise) for the usual operations of nginx-log-audit.sh.
- Reason: Operations were only reachable through command-line options. The menu offers them by number, shows the configuration read, and asks for confirmation before operations that change the system.
- Changes:
  - New option --menu (terminal required). Entries: rapport du jour, statistiques, fail2ban, journal des bannissements, réévaluation, export des bannissements; configuration read (c or the menu item); change log (--changelog); quit.
  - Each entry runs this program again with the options received on the command line (except --menu) plus its own option. Entries that change the system ask for confirmation first.
  - Shared library apps/_menu.sh (new): dialog when installed, text menu otherwise, with a note to install dialog.
  - Help: --menu listed in alphabetical order. --help, --version and --changelog keep their priority over --menu.
  - Files: nginx-log-audit.sh, apps/_menu.sh (new), nginx-tools-tests/test_menu.py (new), CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - Without a terminal, --menu refuses with an error and exit code 1; nothing is run.
  - The menu relaunches the program only; root checks, locks and confirmations stay those of the operation itself.
- Checks:
  - test_menu: --menu listed in the help, refused without a terminal.
  - Manual test in a pseudo-terminal (text menu and stand-in dialog) on read-only entries.
  - Other tests of the program and conventions: see the pull request.
- Action required: none. To get the graphical menu: sudo apt install dialog.

### 2.60.20261028.201441 - --ban-sqli: context for each address, and no bulk ban of normal Odoo users

- Title: --ban-sqli shows, for each address, its reverse DNS name, its owner and country, the Odoo accounts it logged in with, its cart/order/payment requests and its most requested URLs. An address with normal Odoo activity is never banned in bulk.
- Reason: Before banning, the operator must be sure that the address is not a customer doing a normal transaction in Odoo. The report did not show who the address is, and the bulk ban did not check the logins already known to the script.
- Detail: New functions dns_inverse (reverse name, confirmed when the name points back to the address), proprietaire_ip (owner and country through apps/_reseau.py, RDAP), sqli_contexte (one pass over the site logs, rotations included, for the cart, order and payment requests with a 2xx/3xx answer, and the five most requested URLs without query string), champ_ctx. Logins come from the journal already read for the report (charger_logins, logins_odoo). New option --no-lookup: no DNS or RDAP request, only the logs are read. Addresses with a login or an order are marked [NORMAL] in the bulk ban and counted in the summary; they are banned by hand with --ban IP.
- Bugs fixed: the red "!! réponse 2xx" line was shown for every address when the output was not a terminal (the colour variables are empty, so the comparison was always true). It is now a flag.
- Guard rails and edge cases: the context is read only for the addresses of the list; a DNS timeout gives "aucun" or "NON confirmé" after 5 s; without python3 or _reseau.py the owner is "inconnu"; an address with no PTR is not reported as suspicious by itself; the lookups do not change any file.
- Files: nginx-log-audit.sh, nginx-tools-tests/test_nginx_log_audit.py (new test: an address with a login and an address with an order are never banned in bulk, the attack-only address is), CHANGELOG.md.
- Checks: test_nginx_log_audit (126 tests in the run, including the new one), test_conventions (changelog order), test_docs, test_alignement: OK. test_i18n: the 27 untranslated strings of nginx-log-audit, the nginx-hardening strings and odoo-warmup were already failing on origin/main; the 24 new strings of this version are translated in lang/nginx-log-audit.en.po. The test_sbin_ajoutes test fails only in the full run (sandbox PATH) and passes alone, on main too. ShellCheck 0.11.0 on nginx-log-audit.sh: clean at the default level.
- Limits: the text of the new lines is in French, like the rest of --ban-sqli; the English translation (lang/) is not done. The RDAP owner is the holder of the address block, not always the ISP. The Odoo login comes from the systemd journal (100 days): an account used from another address is not seen.
- Action required: none. For a quick check without DNS or RDAP requests: sudo nginx-log-audit.sh --ban-sqli --no-lookup.

### 2.59.20261028.174500 - --ban-sqli: skip addresses already banned

- Title: --ban-sqli bans only the addresses that are not already banned, and says where each one is banned.
- Reason: A second run banned the same addresses again and printed [OK] for each, which hid the real state.
- Detail: New function ip_deja_bannie (iptables -C INPUT DROP, ufw deny, fail2ban banned lists). In the detail, a line "déjà bannie : ..."; during the ban, [DÉJÀ] and no ban call. The summary gives the counts: banned now, already banned, not banned.
- Files: nginx-log-audit.sh, CHANGELOG.md.
- Checks: test with a fake iptables (one address already in DROP): it is skipped and marked, the others are not changed. ShellCheck 0.11.0: clean.
- Note: a fail2ban ban expires after its duration (24 h on this server): an address banned only by fail2ban is counted as already banned until it expires.
- Action required: none.

### 2.58.20261028.173500 - --ban-sqli: first and last date on one line

- Title: The first and last dates of each address are printed on one line, separated by two tabulations.
- Reason: Requested by the operator, to read the time span of each address more quickly.
- Files: nginx-log-audit.sh, CHANGELOG.md.
- Action required: none.

### 2.57.20261028.165800 - --ban-sqli: colours for addresses that reached Odoo

- Title: In the --ban-sqli list, addresses with a 2xx answer are shown in red, with a warning line, and a summary line before the question.
- Reason: A 2xx answer means the request reached Odoo (not refused by nginx). That is the information that matters most before banning.
- Detail: Red for the address, status and warning line when a status is 2xx; magenta for the other addresses (refused 404); bold for the SQL pattern. Colours only on a terminal (no codes when redirected).
- Files: nginx-log-audit.sh, CHANGELOG.md.
- Checks: sample logs with one 200 and one 404: colour codes in the right places; the answer "n" banned nothing. ShellCheck 0.11.0: clean.
- Action required: none.

### 2.56.20261028.164512 - --ban-sqli shows the details of each address before the confirmation

- Title: For each address that attempted an SQL injection: first and last date, status codes, sources, SQL pattern found, user agents and an example request.
- Reason: Before banning many addresses, the operator needs to check the requests (dates, agents, part of the SQL) to be sure they are attacks.
- Detail: New list, most active address first, printed before the question. Each request is read once per source file (blocked-probes.log, access.log, the site log). The SQL pattern is the part of the request that matched the signature. The example request is cut at 200 characters, user agents at 90 characters.
- Files: nginx-log-audit.sh, CHANGELOG.md.
- Guards: the ban itself is unchanged (same list of addresses, same protections, same confirmation). Temporary files are removed on every exit path. Fields are separated by character 0x1F, so empty fields (no status, no pattern) are kept.
- Bug fixed while testing: awk added a leading ", " to the first value of each list (created the element before testing it).
- Checks: manual run on sample logs (two addresses, three requests): dates, statuses, sources, patterns, agents and examples correct; the confirmation answered "n" banned nothing. test_nginx_log_audit: 48 tests OK. ShellCheck 0.11.0: clean.
- Action required: none. The next run of --ban-sqli shows the details before asking.

### 2.55.20261028.161044 - --ban-sqli: sources read from several logs

- Title: --ban-sqli reads the attacker addresses from blocked-probes.log and access.log correctly.
- Reason: Version 2.54 searched several log files at once. grep then prefixes each line with the file name, so the first field was "/var/log/nginx/blocked-probes.log:82.121.129.96" instead of the address. Every source was therefore ignored ("pas une adresse IP") and nothing could be banned.
- Detail: grep -h (without file names) in the --ban-sqli search. Nothing else changes: same signature, same protections (team addresses, server, ban journal).
- Files: nginx-log-audit.sh, CHANGELOG.md.
- Checks: manual run on sample logs (blocked-probes.log and access.log): the addresses are listed, a team address is still refused by --ban.
- Action required: none. The server needs the program updated (git pull or the installed copy).

### 2.54.20261028.104800 - --ban-sqli reads the logs where the attacks are recorded

- Title: --ban-sqli also reads blocked-probes.log and access.log, and recognizes INFORMATION_SCHEMA and WAITFOR DELAY.
- Reason: The first version read only the production access log. On 2026-10-28 the injection requests were refused by nginx (404) and recorded in blocked-probes.log, so --ban-sqli found nothing. The local jail nginx-sqli (jail.local) reads the same logs as this version.
- Changes:
  - The search covers the site access log, /var/log/nginx/blocked-probes.log and /var/log/nginx/access.log (when readable, no duplicate).
  - Signature: INFORMATION_SCHEMA and WAITFOR (space, %20 or +) DELAY added, as in the local filter.
  - Files: nginx-log-audit.sh only.
- Bugs fixed: the empty result for the 2026-10-28 attacks (wrong file, not a wrong ban).
- Safeguards and edge cases:
  - Bans still go through --ban (protected addresses refused and shown as SKIP).
  - A grep for the word "union" alone gives false positives (the French word "réunion" in calendar links): the signature requires UNION followed by SELECT.
- Checks:
  - bash -n and ShellCheck (v0.11.0): no warning.
  - test_nginx_log_audit: see the pull request.
- Action required: none beyond running sudo nginx-log-audit.sh --ban-sqli after merge, if needed.

### 2.53.20261028.100500 - --ban-sqli: ban the sources of SQL injection attempts found in the access log

- Title: Option --ban-sqli bans the addresses that sent SQL injection attempts.
- Reason: On 2026-10-28, automated SQL injection attempts against /es/shop?order= (UNION ALL SELECT, EXTRACTVALUE, ORDER BY n, comment sequences) came from about twenty addresses in a few minutes. Odoo rejected each one with HTTP 400, but no jail banned them: nothing in nginx or fail2ban watches the access log for these payloads.
- Changes:
  - New option --ban-sqli (no argument). It reads the active access log (ACCESS_LOG), keeps the lines matching SQLI_RE (UNION [ALL] SELECT, EXTRACTVALUE(, UPDATEXML(, ORDER BY <digit>, ELT(<digit>, CONCAT(0x7e, SLEEP(<digit>, BENCHMARK(<digit>), counts the requests per address, and lists them, most active first.
  - Confirmation requested before banning (or no question with --yes). Each address is banned by calling --ban IP --yes --reason "injection SQL (--ban-sqli) : N requête(s) ...", so every protection of --ban applies (team addresses, server addresses, ban journal, --unban to undo).
  - The option needs root, like --ban. Exit code 0 when nothing is found or when the run ends.
  - Help text: new line for --ban-sqli, between --ban-history and --ban-threshold (alphabetical order kept).
  - Files: nginx-log-audit.sh only.
- Bugs fixed: none (new option).
- Safeguards and edge cases:
  - The signature is deliberately narrow: a legitimate sort such as order=website_sequence%20asc does not match (checked on sample lines).
  - Addresses are only banned through --ban, never with a direct firewall command: protected addresses are refused there and reported as [SKIP].
  - Lines that do not start with an IP address are listed as ignored.
  - Temporary file created with mktemp and removed on every exit path of the option.
- Checks:
  - bash -n and ShellCheck (v0.11.0): no warning.
  - Signature tested on five sample lines: the three injection lines match, a plain order= sort and a plain 200 request do not.
  - nginx-tools-tests: test_nginx_log_audit (48 tests) OK; test_conventions for this changelog entry.
- Action required: run `sudo nginx-log-audit.sh --ban-sqli` (confirmation shown) to ban the addresses already seen. Preventive jail (nginx-sqli filter, nginx rule on $args) is a separate change, not included here.

### 2.52.20261026.230003 - curl rate-limited instead of blocked; service-worker prefetch and icon requests no longer count as hostility

- Title: curl is no longer blocked by user agent (nginx-odoo-config 1.12: one curl every 5 seconds; a second one in the window gets 429). The audit no longer counts service-worker prefetches as a page burst, nor browser icon requests as catch-all hostility.
- Reason: (a) The owner asked that curl not be blocked, except when several curl requests arrive within 5 seconds from the same address. (b) A friend's home address (67.55.21.165) was banned for 24 hours by the fail2ban jail nginx-catchall: 16 hits in one second, all Safari requests for `/apple-touch-icon.png`, `/apple-touch-icon-precomposed.png` and `/favicon.ico` on `ctf1.services-conseils-linux.org`, an old host name that pointed to PROD (51.161.38.12) and has been removed from DNS. (c) The audit counted those icon hits as hostility, and a 14-page burst as a sign of a script. The burst came from the service worker (`/en_CA/event/service-worker.js` prefetching pages, Referer `.../service-worker.js`): Odoo legitimately returns several pages per second, so the owner's point is correct. Burst requests with a `/web/image/` path were already excluded (STATIC_RE).
- Changes:
  - nginx-odoo-config 1.12 (separate project, VERSION updated):
    - `conf.d/bot_blocker.conf`: `curl` removed from the bad-bot regex (python-requests, python-httpx, python-urllib and Wget are still blocked); the comment explains the new rate limit.
    - `conf.d/odoo-global.conf`: `map $http_user_agent $is_curl_client` (`"~*^curl/"`), `map "$is_curl_client:$is_internal_client:$is_trusted_ip" $limit_key_curl` (key = client address only for a curl client that is neither 127.0.0.1 nor a trusted IP), `limit_req_zone $limit_key_curl zone=odoo_curl:10m rate=12r/m`.
    - `snippets/securite-commune.conf`: new rule 1 bis, `limit_req zone=odoo_curl burst=0 nodelay;` at server level (inherited by the locations that declare no limit_req, such as the static cache and `location = /robots.txt`).
    - `snippets/odoo/_odoo-common.conf`: the same line added to the three locations that declare their own limit_req (`location` for the apple-touch-icon, `location /`, `location ~ ^/web_editor/shape/`), because nginx does not merge a parent limit_req with a child one.
    - `README.md` is not changed by this version; the README lines about curl describe the server-local exception, which is unchanged.
  - nginx-log-audit.sh:
    - `scan_ips()`: the page burst ignores a request whose Referer (field 4) ends with `/service-worker.js` (optional query string). The requests still count in the totals.
    - New function `compter_catchall IP`: prints "hostile icon" counts for one address from the merged catch-all log. An icon is a `GET` or `HEAD` of `/apple-touch-icon*` or `/favicon.ico`.
    - `investigate_and_propose()`: the catch-all criterion uses only the hostile count; icon-only traffic is reported as "non hostiles" and does not add to the score.
    - `evaluer_bannissement()` (used by `--unban-check` and `--unban-low-score`): an address with no site request and only icon requests on the catch-all sensor gets the verdict "lever" (lift recommended) with an explicit message. Previously it fell through to "trace".
    - Tests (nginx-tools-tests/test_nginx_log_audit.py): `test_rafale_du_service_worker_ne_compte_pas_mais_une_vraie_rafale_oui` (16 pages with the service-worker Referer: no burst; the same 16 pages without it: burst of 16) and `test_icones_du_capteur_catchall_ne_justifient_pas_le_bannissement`.
    - Tests (nginx-tools-tests/test_config_nginx.py): `test_filtre_a_robots` no longer expects curl to be blocked and checks that an isolated curl is not blocked by user agent; `test_curl_limite_par_rafale_et_non_bloque_par_ua` and `test_curl_repete_dans_chaque_location_qui_a_son_propre_limit_req` are new.
    - Catalogue `lang/nginx-log-audit.en.po`: five new messages (icon requests, "(also, ", "no request on the site").
  - Files touched: nginx-log-audit.sh, CHANGELOG.md, lang/nginx-log-audit.en.po, nginx-tools-tests/test_nginx_log_audit.py, nginx-tools-tests/test_config_nginx.py, nginx-tools-tests/run-all.sh (SCRIPT_VERSION), doc/nginx-tools.version, nginx-odoo-config project (VERSION 1.12.20261026.230003 and 5 files above).
- Bugs fixed:
  - Symptom 1: a curl test from outside returned 403 (bot blocker). Diagnosis: curl in the bad-bot regex of bot_blocker.conf. Fix: rate limit instead.
  - Symptom 2: a friend's address was banned for 24 h with score 1/7 and no proposal to lift it. Diagnosis: the catch-all criterion counted icon requests as hostility (hostile = 1) and the burst criterion counted service-worker prefetches (14 pages in 10 s). With both, the verdict was "garder". Fix: both exclusions above. Expected verdict for that address with the same logs: no hostile sign, so "lever".
- Safeguards and edge cases:
  - curl limit: `rate=12r/m` with `burst=0 nodelay`: the first request passes, a second one within the next 5 seconds is refused with 429 (`limit_req_status 429` is already set). A single curl every 5 seconds or more is never refused. Localhost (`$is_internal_client`) and trusted addresses (`$is_trusted_ip`) are exempt, as for the other limits. Only the User-Agent prefix `curl/` is limited; a client that changes its User-Agent is handled by the other rules, not by this one.
  - Known limit: the curl limit does not exempt a request sent to the server's own public address (`$remote_addr = $server_addr`). Odoo's self-calls use python-requests, which the limit does not touch.
  - Referer exclusion: the Referer header is set by the client. A scanner can forge `.../service-worker.js` to avoid the burst criterion. Only that criterion changes; the other hostility criteria (catch-all, sensitive files, errors, fake search engines) still count.
  - Icon exclusion: only `apple-touch-icon*` and `favicon.ico`. Any other catch-all request still counts, including `/apple-touch-icon.png` when it is part of a longer scan (the scan's other requests still count).
  - Verdicts: `--unban-check` and `--unban-low-score` use the same function (`evaluer_bannissement`), so both change together.
  - nginx limit_req inheritance: a location that declares any limit_req does not inherit the server-level one, so the line is repeated in each such location. A test checks this for `_odoo-common.conf`.
- Checks:
  - nginx-odoo-config: `python3 -m unittest test_config_nginx` with NGINX_ODOO_DIR pointing to the 1.12 tree: 32 tests, OK (2 skipped). `nginx -t` NOT run: nginx is not installed in the sandbox.
  - nginx-log-audit.sh: `bash -n` OK; the two new tests pass; `test_nginx_log_audit` full run and `test_i18n` nginx-log-audit catalogue pass.
  - The odoo-warmup i18n failure is pre-existing on main and unrelated.
- Action required:
  - PROD and DEV: deploy nginx-odoo-config 1.12 (conf.d, snippets). Run `nginx -t` before `systemctl reload nginx`. Not verified here.
  - PROD: `fail2ban-client set nginx-catchall unbanip 67.55.21.165` (the friend's address).
  - Decision still open: the 64.89.160.73 re-ban on DEV (see 2.50).

### 2.51.20261026.222540 - Numeric order of addresses; catch-all hits counted in the score

- Title: Addresses listed in numeric order (13.x before 104.x); a catch-all hit now adds to the score.
- Reason: (a) `--unban-check` and `--unban-low-score` listed addresses in alphabetical order (104.x before 13.x). (b) A friend's home address (Quebec, Distributel) was banned by the fail2ban jail nginx-catchall; `--investigate` printed "Signes d'hostilité : 2" but "Score 1/7" and "d'automatisation : -1", which cannot both be right. The catch-all branch counted the hit as hostility but never as a criterion of the score. (c) A friend's curl test returned 403: this is the bot blocker (bot_blocker.conf), which refuses curl user agents on purpose; it is not a bug.
- Changes:
  - `list_manual_bans()`: `sort -V -u` (version sort) instead of `sort -u`.
  - `--unban-low-score`: `sort -V` for the list of addresses (table and evaluation order).
  - `investigate_and_propose()`, catch-all branch: `score=$((score+1))` next to the hostility count, like the other criteria.
  - Test: `test_unban_low_score_ordre_numerique_des_ip` (new); the PTY test `test_unban_check_leve_meme_si_le_fichier_n_est_pas_executable` answers the prompts in numeric order.
  - Files touched: nginx-log-audit.sh, nginx-tools-tests/test_nginx_log_audit.py, CHANGELOG.md, nginx-tools-tests/run-all.sh (SCRIPT_VERSION), doc/nginx-tools.version.
- Bugs fixed:
  - Symptom: 104.x listed before 13.x; a catch-all hit shown as hostility but missing from the score; automation count negative (-1).
  - Diagnosis: `sort -u` is lexical; the catch-all branch increments `hostile` without `score`.
  - Fix: `sort -V`; `score` incremented as well.
- Safeguards and edge cases:
  - Verdicts (`--unban-check`, `--unban-low-score`) depend on the hostility count, not on the score: this change alters the displayed score only, not which addresses are lifted.
  - The score of an address seen only on the catch-all sensor (no site request) is still not computed (shown "?/7"); the verdict column is the decision.
- Checks: bash -n, ShellCheck 0.11.0 clean, test_nginx_log_audit OK (46 tests). test_i18n: nginx-log-audit catalogue passes; the odoo-warmup failure is pre-existing on main.
- Action required: none for the code. Open points: (1) a browser asking for Apple touch icons or favicons on a host that nginx does not serve counts as catch-all hostility (friend's case: 16 hits on ctf1.services-conseils-linux.org, 24 h fail2ban ban); decide whether those requests should be excluded, or the host served. (2) Friend's home address: `fail2ban-client set nginx-catchall unbanip 67.55.21.165` on PROD if the ban must end before 2026-10-27 18:13.

### 2.50.20261026.220229 - --unban-low-score uses the --unban-check verdict; one process; one progress line per address

- Title: `--unban-low-score` lifts only what `--unban-check` recommends; it runs in one process, shows one step per address, and reads the Odoo journal once.
- Reason: On DEV, `--unban-low-score` lifted 64.89.160.73 (score 2/7) and 45.138.12.52 (score 1/7). Both had been judged "a garder" (keep) by `--unban-check` the same day: 3 hostility signs and a scanner for the first, one sign for the second. The two modes disagreed because the low-score mode decided on the score alone. The administrator also asked for less noise and a shorter run (about 155 s for 30 addresses, each sub-investigation rereading the Odoo journal and printing its own headers).
- Changes:
  - New function `evaluer_bannissement IP`: the body of the `--unban-check` loop, moved unchanged into a function. `--unban-check` and `--unban-low-score` both call it, so the verdict is the same.
  - New function `preparer_journaux_unban`: the log merge done once per run, shared by both modes.
  - `--unban-low-score`: an address is lifted only when the verdict is "lever". The score is still shown. No sub-process per address: the investigations run in the same process, so the Odoo journal (`charger_logins`) is read once per run.
  - Output: one step per address, "Réévaluation n/N : IP (lecture seule)", the table gets a "--unban-check" column (LEVÉE recommandée, garder, à vérifier, sans trace, incohérente), and the details of each evaluation are not printed.
  - `decide_unban()`: no question while evaluating (`MODE_EVALUATION`), so the only prompt is the one of `--unban-low-score`.
  - `investigate_and_propose()`: remembers the score of the evaluation (`DERNIER_SCORE`).
  - Help text, header comment, doc/en/nginx-log-audit.conf.example and lang/nginx-log-audit.en.po updated.
  - Files touched: nginx-log-audit.sh, lang/nginx-log-audit.en.po, nginx-tools-tests/test_nginx_log_audit.py, doc/en/nginx-log-audit.conf.example, CHANGELOG.md, nginx-tools-tests/run-all.sh (SCRIPT_VERSION), doc/nginx-tools.version.
- Bugs fixed:
  - Symptom: an address judged "a garder" by `--unban-check` was lifted by `--unban-low-score`.
  - Diagnosis: two decision rules (score for the low-score mode, verdict for `--unban-check`).
  - Fix: one rule, the verdict.
  - Symptom: 20 of 30 addresses showed "?/7" and could never be proposed.
  - Diagnosis: the investigation prints a score only on some branches. The new table shows the verdict for every address, so these addresses are now assessed (catch-all and refusal evidence).
- Safeguards and edge cases:
  - A protected address (team, protected place) is never lifted, as before.
  - An address whose verdict is "verifier", "trace" or "incoherente" is never lifted.
  - Without a terminal, the list is shown and nothing is lifted, unless --yes is given.
  - The log merge happens once: a log that changes during the run is read as it was at the start.
- Checks: bash -n, ShellCheck 0.11.0 clean, test_nginx_log_audit OK (45 tests). The low-score test now covers two cases: an address judged "garder" is never lifted (even at a low score), and an address judged "lever" is lifted with --yes. test_i18n: the nginx-log-audit catalogue passes (10 msgids added); the odoo-warmup failure is pre-existing on main.
- Action required: on DEV, consider re-banning 64.89.160.73 (scanner: 507 catch-all attempts, 238 sensitive-file requests), which 2.49 lifted by mistake: nginx-log-audit.sh --ban 64.89.160.73 --reason "...". Then review 45.138.12.52 with --unban-check.

### 2.49.20261026.213805 - --unban-low-score: one-digit score, visible progress, loopback excluded from section 3

- Title: Low-score list shows a correct score and progress steps; 127.0.0.1 is no longer a false positive in section 3.
- Reason: Review of the output of `--unban-low-score` (PROD and DEV, 2026-10-26): (a) the scores were shown as "3" then "7/7" on two lines, so no address was under the threshold, and the program still printed "Aucune IP bannie n'a un score sous 3/7" under a table listing scores 0 to 6; (b) the command was silent for several minutes; (c) section 3 of the daily checks listed 127.0.0.1 (local requests) as an address that was refused and also served a 200.
- Changes:
  - `--unban-low-score`: the score is read from the "N/7" line only, with a sed that does not match the word of the line (`grep -o '[0-9]'` returned both the 3 and the 7 of "3/7").
  - `--unban-low-score`: one step per address on the error output, "Score n/N : IP (enquête en lecture seule)" (shown in a terminal or with --verbose only). The investigation's own progress lines are no longer discarded (stderr is no longer sent to /dev/null for the investigation run).
  - `revue_controles()`, section 3: 127.0.0.1 and ::1 are excluded from the access-log side of the comparison.
  - Files touched: nginx-log-audit.sh, lang/nginx-log-audit.en.po (new msgid " (enquête en lecture seule)"), nginx-tools-tests/test_nginx_log_audit.py (new test), CHANGELOG.md, nginx-tools-tests/run-all.sh (SCRIPT_VERSION), doc/nginx-tools.version.
- Bugs fixed:
  - Symptom: table row "3" / "7/7" and "Aucune IP bannie n'a un score sous 3/7" in the same output.
  - Diagnosis: the extraction kept every digit of the matched "Score N/7" text; the two-digit value failed the numeric test, so no address was ever proposed.
  - Fix: one digit, from the Score line only.
  - Symptom: 127.0.0.1 listed in section 3.
  - Diagnosis: the check compares every address with a 200 in the access logs; local checks on the server are 200 responses for the same address refused in blocked-probes.log.
  - Fix: loopback excluded.
- Safeguards and edge cases:
  - An address with no "Score" line in its investigation keeps "?/7" and is never proposed (unchanged). This is a known limit: the investigation prints a score only on some branches (for example none for an address seen only on the catch-all sensor). Extending this to a score is a separate change to decide.
  - The investigation run is no longer silenced on stderr: its errors, if any, now appear on the error output.
  - The progress line is off in a pipe or a scheduled task.
- Checks: bash -n, ShellCheck 0.11.0 clean, test_nginx_log_audit OK (45 tests, including the new test: one-digit score, "Score 1/1" step line), test_i18n: nginx-log-audit catalogue passes; the odoo-warmup catalogue failure is pre-existing on main.
- Action required: decide whether the "?/7" addresses (no score line) should get a score, or be listed as "score non calculable" in --unban-low-score. None for this version.

### 2.48.20261026.212654 - Fix "comm: write error: Broken pipe" in the daily checks section

- Title: Section 3 of the daily checks: no more broken pipe, and no more empty result under pipefail.
- Reason: The daily `--unban-check` output (PROD, 2026-10-26) printed "comm: write error: Broken pipe" in section 3 ("Adresses refusées par nginx et servies normalement (200)"). The administrator asked for it to be fixed.
- Diagnosis: `comm -12 ... | head -n 10` closed the pipe after ten lines. When the list is long enough, `comm` gets SIGPIPE (exit 141). With `set -o pipefail`, the `|| croise=""` fallback then emptied the result, so section 3 could print "[OK] aucune adresse" even when addresses matched.
- Changes:
  - `revue_controles()`, section 3: `head -n 10` replaced by `awk 'NR <= 10'`, which reads the whole stream and never closes it early, so `comm` never receives SIGPIPE and the result is kept.
  - Files touched: nginx-log-audit.sh, CHANGELOG.md, nginx-tools-tests/run-all.sh (SCRIPT_VERSION), doc/nginx-tools.version.
- Bugs fixed:
  - Symptom: "comm: write error: Broken pipe" on stderr; the section could report "[OK]" when addresses matched.
  - Diagnosis: pipe closed by `head` while `comm` still wrote (reproduced: 300,000-line inputs gave exit 141 with the old pipeline, none with the new one).
  - Fix: see above.
- Safeguards and edge cases: the list is still limited to 10 addresses; with fewer than 10 matches the output is unchanged; the other `| head` pipelines of the script were not changed because they read a finite, already-complete input.
- Checks: bash -n, ShellCheck 0.11.0 clean, test_nginx_log_audit OK (44 tests), reproduction of the old and new pipelines.
- Known point, not changed in this version: section 3 lists the refused URLs of each address and includes 127.0.0.1 (local requests). The loopback address should probably be excluded from this check; to be decided.
- Action required: none.

### 2.47.20261026.210405 - Log reading shown as one line with one dot per log file

- Title: Quieter progress output: one "Lecture des journaux" line, then one dot per log file read.
- Reason: The run printed one progress line per rotated log file ("Lecture du journal 1/39 : ..."), 39 lines for one address. The administrator asked for a short progress line instead, and sent the daily `--unban-check` and `--investigate` output as text to review.
- Changes:
  - `merge_all_rotations()`: prints "Lecture des journaux" once (when at least one file is read), then one "." per file read (" ." after the first). The per-file line is kept and shown only with `--details`.
  - New helpers `progres_point N` (one dot, shown with --verbose or on a terminal, not with --details) and `progres_fin_points N` (ends the dot line with a newline).
  - Files touched: nginx-log-audit.sh, lang/nginx-log-audit.en.po (new msgid "Lecture des journaux"), nginx-tools-tests/test_nginx_log_audit.py (progression test run with --details; new test for the dots), nginx-tools-tests/run-all.sh (SCRIPT_VERSION), doc/nginx-tools.version.
- Bugs fixed: none in this version (display change only).
- Safeguards and edge cases: no dot line when no file is read (no header either); the dot line is never printed in a pipe or a scheduled task (progress is off there); with --details the dot line is replaced by the per-file lines, so the two never mix; the dot line ends with a newline before the next progress message.
- Checks: bash -n, ShellCheck 0.11.0 clean, test_nginx_log_audit 44 OK (new test: header, no per-file line, ". . ." for three files). test_i18n: the nginx-log-audit catalogue passes; the odoo-warmup catalogue failure is pre-existing on main and unrelated.
- Action required: none.

### 2.46.20261026.195327 - Unban review: refusals count, single bursts to check, coherence guard, daily checks

- Title: Unban review: refused-only bans are justified, single bursts are flagged, coherence guard, daily checks section.
- Reason: Review of the 87 manual bans listed by `--unban-check` (2026-10-26). Three problems: (a) several addresses were reported "without trace" although they were refused again and again (blocked-probes.log was never read by the re-evaluation); (b) the investigation of 192.54.244.135 printed the reverse DNS, the host lookup and the grep of another address (34.179.161.77), so its verdict rested on the wrong evidence; (c) a single burst of pages was enough to keep a ban. The administrator also wants a daily list of points to re-check, with the commands run by the program itself.
- Changes:
  - `--unban-check`:
    - an address without any request on the site or on the catch-all sensor is now checked in `blocked-probes.log`: repeated refusals justify keeping the ban ("requêtes REFUSÉES par nginx");
    - an address with no evidence left shows its ban history (`afficher_bannissements`: fail2ban jails, ban log) instead of a bare "no trace";
    - two new verdicts: "à vérifier" (only one burst of pages and no strong sign) and "incohérente" (no verdict, the investigation must be run again). Neither lifts a ban by itself;
    - new section "AUTRES POINTS À RE-VÉRIFIER" (function `revue_controles`, read-only, printed after the BILAN and also when there is no manual ban): 1) team and protected addresses among the bans; 2) fail2ban jails and number of banned addresses per jail; 3) addresses refused by nginx that also received 200 pages (possible false positive); 4) logs used by the checks; 5) the commands to run by hand for each address to re-check;
    - the BILAN line gives the counts of "à vérifier" and "incohérente".
  - `investigate_and_propose`: remembers the address asked for; a coherence check before the "Pour vérifier soi-même" lines marks the investigation as inconsistent when the address changed; sets a strong-sign flag (`SIGNE_FORT`) for sensitive files, errors, fake search engine and catch-all.
  - `decide_unban`: returns "incohérente" when the investigation is inconsistent, and "à vérifier" when the only sign is a burst of pages.
  - New global variables: `ENQUETE_INCOHERENTE`, `SIGNE_FORT`, `REVOIR_IPS`.
  - Files: nginx-log-audit.sh, lang/nginx-log-audit.en.po (30 new entries), doc/en/02-nginx-log-audit.md and doc/fr/02-nginx-log-audit.md (section "Reviewing manual bans every day"), nginx-tools-tests/test_nginx_log_audit.py (2 tests), nginx-tools-tests/run-all.sh (1.197), doc/nginx-tools.version (1.146).
- Bugs fixed:
  - Symptom: `--unban-check` showed, for 192.54.244.135, the reverse DNS, the host command and the grep of 34.179.161.77; the verdict was based on another address.
  - Diagnosis: the address used by the DNS and grep lines changed between the header of the investigation and the DNS lines. The fixtures of the test suite do not reproduce it, and the statement of the cause in the code is not confirmed yet.
  - Fix: the address is remembered at the start of the investigation; if it differs before the verification lines, the investigation is marked inconsistent (no verdict), and the verification lines use the address that was asked for. The cause itself still has to be confirmed on the real log of the server (see "Action required").
  - Symptom: addresses refused by nginx (blocked-probes.log) were reported "sans trace".
  - Diagnosis: the re-evaluation read only the site access logs and the catch-all log.
  - Fix: blocked-probes.log and the ban history are read (see Changes).
- Safeguards and edge cases:
  - The verdict "à vérifier" never lifts a ban: the decision stays with the administrator.
  - The new section is read-only: no firewall rule, fail2ban jail or ban log is changed by it.
  - Missing logs (blocked-probes.log, access log, fail2ban.log) are reported as [ATTN] or "nothing to compare"; they do not stop the program.
  - An empty list of manual bans still prints the section.
  - `--unban-check` still requires root (firewall rules).
- Version: 2.46 (not 2.45): main already released 2.45 (summary of the IPs to unban). Both features are kept.
- Checks:
  - `bash -n` and ShellCheck 0.11.0 (no warning).
  - `test_i18n`: 32 tests OK (every new message has an English entry).
  - `test_nginx_log_audit`: 43 tests OK (41 existing and 2 new: refusals justify a ban; a single burst is "à vérifier" and appears in section 5).
  - Not run on the production servers.
- Action required:
  - Run `nginx-log-audit.sh --unban-check` on each server and send the sections 1 to 5 of the output for a review.
  - Re-run `--investigate 192.54.244.135` (the investigation of this address was inconsistent).
  - Check the address 140.82.7.85 by hand (its only sign is a burst of pages).
  - For a daily check, add the crontab line shown in the documentation (section "Reviewing manual bans every day").

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

### 1.31.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: none.
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

### 1.30.20261029.193900 - --max-drop: refuse a list much smaller than the last accepted one

- Title: a sudden drop of the blocklist size stops the update, the ipsets are kept.
- Reason: the script already keeps the current ipsets when the download fails and refuses a list under --min-ips. A truncated download that still passes --min-ips (for example 60 entries instead of 5000) would unban most of the addresses. A relative limit closes that gap.
- Changes:
  - New option --max-drop PCT (default 50, 0 = no check, 100 at most), also key MAX_DROP in the configuration file (config_defaut).
  - New state file last-list.count in the state folder: number of valid entries of the last accepted list, written with last-list.sha256.
  - Check placed after the analysis, before the ipset update, in normal and --dry-run modes (dry-run only reports it).
  - Files touched: sync-crowdsec-blocklist.sh (version 1.30), CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - No check when the cache fallback is used, and none on the first run (no reference yet).
  - A reference of zero is ignored.
  - The message gives the way out (--max-drop 0) when the drop is expected.
- Checks:
  - bash -n OK; --version displays the dynamic version.
- Action required: none. If a legitimate large cleanup of the source happens, run once with --max-drop 0.

### 1.29.20261028.214122 - --menu: catalogue entries for the menu and its help line (English)

- Title: --menu: catalogue entries for the menu and its help line (English).
- Reason: The catalogue test (test_i18n) reported the new --menu strings of this program as untranslated.
- Changes:
  - lang/sync-crowdsec-blocklist.sh.en.po: entries for the menu entries (their English text is shown from the EN field of the menu, so msgstr is empty) and for the --menu help line (English translation).
  - Files: lang/sync-crowdsec-blocklist.sh.en.po, CHANGELOG.md.
- Bugs fixed: symptom: test_i18n failure on this program. Diagnosis: the catalogue had no entries for the new strings. Correction: entries added. The program code is unchanged.
- Safeguards and edge cases: no change in behaviour; the French and English menus are unchanged.
- Checks: test_i18n (catalogues of bash programs).
- Action required: none.

### 1.28.20261028.211449 - --menu: interactive menu of the usual operations

- Title: New option --menu: a menu (dialog when installed, text otherwise) for the usual operations of sync-crowdsec-blocklist.sh.
- Reason: Operations were only reachable through command-line options. The menu offers them by number, shows the configuration read, and asks for confirmation before operations that change the system.
- Changes:
  - New option --menu (terminal required). Entries: synchronisation, essai (--dry-run), état, adresses bloquées, cron, crochet ufw, retrait; configuration read (c or the menu item); change log (--changelog); quit.
  - Each entry runs this program again with the options received on the command line (except --menu) plus its own option. Entries that change the system ask for confirmation first.
  - Shared library apps/_menu.sh (new): dialog when installed, text menu otherwise, with a note to install dialog.
  - Help: --menu listed in alphabetical order. --help, --version and --changelog keep their priority over --menu.
  - Files: sync-crowdsec-blocklist.sh, apps/_menu.sh (new), nginx-tools-tests/test_menu.py (new), CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - Without a terminal, --menu refuses with an error and exit code 1; nothing is run.
  - The menu relaunches the program only; root checks, locks and confirmations stay those of the operation itself.
- Checks:
  - test_menu: --menu listed in the help, refused without a terminal.
  - Manual test in a pseudo-terminal (text menu and stand-in dialog) on read-only entries.
  - Other tests of the program and conventions: see the pull request.
- Action required: none. To get the graphical menu: sudo apt install dialog.

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

## apps/_seuils.py

### 1.0.20261029.212344 - Shared thresholds for web-monitor.py and app-log-live.py

- Title: Shared thresholds for web-monitor.py and app-log-live.py.
- Reason: The same notions were written twice with values that could drift apart (burst: 15 pages in web-monitor.py; the 404 probe threshold and the connection percentage in app-log-live.py). One module now holds them.
- Changes:
  - New module apps/_seuils.py: BURST_PAGES (15), BURST_WINDOW_S (10), CONNECTIONS_PCT (80), PROBE_404 (5), REPEAT_MIN (2). Defaults unchanged.
  - Optional overrides read in order: /etc/default/app-seuils.conf, then ~/.app-seuils.conf (KEY=value; the last one read wins).
  - Invalid or unknown values are ignored with a bilingual warning on stderr; the default is kept.
  - Functions: lire(), valide(), charger() returning (values, files read, warnings).
  - Files: apps/_seuils.py, nginx-tools-tests/test_seuils.py (8 tests).
  - Not changed: nginx-log-audit.sh keeps its own bash values (its --page-burst default is 8 against 15 here; this difference is still to be decided).

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

### 1.5.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: none.
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

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

### 1.4.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: none.
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

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

### 1.4.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: none.
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

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

### 1.21.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: a short catalogue key made from "error(s)" ("errors") was replaced inside option names ("--errors-only" became "--erreurs-only"). Fix: a key that starts with a letter is no longer replaced right after "--" (lookbehind on "--" in Traducteur._remplacer). Checked with test_app_log_live and test_i18n.
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

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

### 1.3.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: none.
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

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

### 1.5.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: none.
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

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

## apps/_logs_merge.py

### 1.1.20261029.230225 - nginx program name "http" (4 characters) so the columns line up with Odoo

- Title: the nginx lines of the merged stream carry the program name "http" instead of "nginx".
- Reason: "nginx" is one character longer than "odoo", so the nginx lines were shifted by one column against the Odoo lines in app-log-live.py --log-nginx. Renaming the program to 4 characters keeps the Odoo lines unchanged.
- Changes:
  - JOURNAL_PROGRAM = "http": the prefix of each nginx line is "<time> <host> http: ".
  - Comment of the header and of the option help updated for --log-nginx.
- Bugs fixed:
  - Symptom: the country, the address and the name of nginx lines were one column to the left of those of the Odoo lines. Diagnosis: the program field "nginx" has 5 characters, "odoo" has 4. Fix: program "http".
- Safeguards and edge cases:
  - The journal format of the prefix is unchanged (same date, offset, host and colon); only the program word changes.
- Checks:
  - nginx-tools-tests/test_logs_merge.py: 9 tests OK (the prefix test expects " http: ").
- Action required: none.

### 1.0.20261029.215532 - Merge of several log streams in time order

- Title: new helper that merges the application journal and the nginx logs in time order, with the same prefix (used by app-log-live.py --logs-nginx).
- Reason: see app-log-live.py 1.115.
- Changes: new file apps/_logs_merge.py (functions journal_instant, nginx_pair, journal_line, Merger, read_stream, main; options --grep, --grep-sensitive, --lines, --nginx, --no-follow, --since, --until, --version, --wait).
- Bugs fixed: none.
- Safeguards and edge cases: see app-log-live.py 1.115 (stalled streams, lines without time, SIGTERM, closed pipe).
- Checks: unit tests in nginx-tools-tests/test_logs_merge.py; manual run on simulated logs.
- Action required: none.

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

### 1.23.20261031.180855 - --correlate: active Odoo accounts at given request times

- Title: new option --correlate reads nginx request times and lists the Odoo accounts active in these times.
- Reason: --investigate of nginx-log-audit.sh must identify the Odoo user behind an address, read from the database (Odoo does not store IP addresses of sessions).
- Changes:
  - New function connexions_proches (base, instants, margin 2 hours): reads, read only, res_users_log (logins), res_users.login_date (last login) and bus_presence (last activity) in the time window. Missing sources are skipped.
  - New function correlate_cli: reads one nginx date per line on standard input, lists BASE, LOGIN, NAME, SOURCE and DATE (local time of the server) for each Odoo database found.
  - main(): option --correlate (alone); usage line updated.
- Bugs fixed: none (new function).
- Safeguards and edge cases: all SQL goes through _requete (read-only transaction forced by PostgreSQL); the time window is built from integers; unreadable databases give an error message and exit code 1; no date means no query.
- Checks performed: py_compile; --version; without root the command prints "bases illisibles" and exits with code 1 (expected in this sandbox).
- Action required: none. Reading the database requires root on the server (PostgreSQL local, as before).

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

### 1.14.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: none.
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

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

### 1.4.20261030.153422 - No plural marker "(s)" in the displayed texts

- Title: the texts shown by the program no longer contain "(s)": "requête(s)" becomes "requêtes", "adresse(s)" becomes "adresses", "lente(s)" becomes "lentes" (French and English).
- Reason: the user asked for the plural marker "(s)" to be removed everywhere in what the programs display.
- Changes: the "(s)" of every displayed text is replaced by "s": the texts of the code, the translations (lang/*.po, msgid and msgstr). Comments, docstrings and the CHANGELOG are not changed.
- Bugs fixed: none.
- Safeguards and edge cases: the plural form is used for every count, including 1 ("1 erreurs"); a singular form for 1 is not generated (not requested).
- Checks: unit tests of the program (expected texts updated), test_i18n (every translated text has its entry).
- Action required: none.

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

### 1.205.20261027.203437 - Test runner: WordPress probes and curl burst 10

- Title: test runner follows the generic nginx configuration 1.14.
- Changes: SCRIPT_VERSION 1.205; doc/nginx-tools.version 1.154; test_config_nginx updated.
- Bugs fixed: none.
- Safeguards and edge cases: none.
- Checks: test_config_nginx, test_conventions.
- Action required: none.

### 1.204.20261027.171700 - Test runner: CHANGELOG convention and nginx-hardening tests

- Title: the test runner version follows the nginx-hardening tests (generic configuration step).
- Reason: the new tests of nginx-hardening.sh 2.56 (generic configuration installed by --update) are part of the suite.
- Changes: SCRIPT_VERSION 1.204; doc/nginx-tools.version 1.153.
- Bugs fixed: none.
- Safeguards and edge cases: none (no behaviour change).
- Checks: test_conventions.
- Action required: none.

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
