# Changelog

Version numbers follow `MAJOR.MINOR.YYYYMMDD.HHMMSS` (local time of the change).
Each program has its own section; the most recent version comes first.
Earlier history was archived outside this repository when this file was created.

## admin-menu.sh

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
