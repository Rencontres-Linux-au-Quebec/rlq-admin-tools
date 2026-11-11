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

### 1.3.20261109.190000 - Erase key (^H) in the menu

- Title: the choice of the menu and the confirmations accept ^H and ^?.
- Reason: report of the administrator on 2026-11-09.
- Changes: the 3 questions "tty_ligne; read -r -p" become "read -e"; apps/_menu.sh (4 questions) likewise; apps/_menu.py _saisie() now calls apps/_i18n.py saisie().
- Bugs fixed: symptom: in a question, the erase key showed "3^H^H" and the answer kept the ^H characters; diagnosis: the kernel line mode (stty icanon echoe, put back by tty_ligne) knows ONE erase key only (stty erase, usually ^?), while some terminals (PuTTY, some ssh clients) send ^H; ECHOE does not help when the key is not the erase key; fix: the answers are edited by readline (read -e) or by our own line editor, where ^H AND ^? erase.
- Safeguards and edge cases: dialog mode unchanged.
- Checks performed: test_saisie_terminal, test_menu [OK].
- Action required: none.

### 1.2.20261101.231500 - Retour arrière : écho et effacement rétablis avant chaque réponse

- Title: the menus of admin-menu.sh (choice, Enter to return, yes/no) restore echo and erase first.
- Reason: Request of the administrator: in nginx-hardening.sh, at the prompt "Faire le setup du courriel (relais SMTP) maintenant ? [o/N] :", the Backspace key shows "d^H^H^H^H" and erases nothing. The same problem can hit every program that asks a question, so every interactive prompt of the Bash and Python programs must be checked and fixed.
- Changes: tty_ligne before the three reads of admin-menu.sh (yes/no helper, the choice, the return key). The menu libraries apps/_menu.sh (4 reads, tty_ligne and fallback) and apps/_menu.py (its own line reader _saisie(), with ICANON, ECHO, ECHOE set, then restored) are changed the same way.
- Bugs fixed: same symptom as nginx-hardening.sh 2.74. Diagnosis and fix as in apps/_i18n.py 1.22.
- Safeguards and edge cases: Without a terminal (pipe, cron, stdin not a tty): nothing is changed, the programs behave as before. Stdin and /dev/tty redirections are guarded with || true (set -e). Password prompts (read -s) are not changed. The helper is defined in apps/_i18n.sh; a program without that file gets a no-op fallback. apps/_menu.py: without termios (Windows) input() is used.
- Checks performed: bash -n; nginx-tools-tests/test_saisie_terminal.py (new, static): every interactive read -p / read -e of the Bash programs has tty_ligne on its line; tty_ligne is defined and sets icanon echo echoe; saisie() is defined and used by the i18n context; apps/_menu.py has its own line reader; versions.
- Action required from the user: none.

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

### 2.35.20261110.193238 - Traversal test out of the hourly run: only at nginx-hardening.sh --update or with --traversal-only

- Title: the traversal test of the query string is no longer sent at every hourly run; it runs once per update of the nginx rules.
- Reason: web-monitor.py runs app-health-check.py every hour. The traversal test sends GET /some/page?file=../conf/conf.php, which nginx refuses with a 404 on purpose. The result never changes between two hours (the rule does not change without an update), so the hourly 404 added noise to the logs (app-log-live.py shows it as "[sonde de ce serveur]").
- Changes: new function check_traversal(cfg, target, verbose) with the same request, the same rule and the same result text; check 11 removed from check_http() (replaced by a comment). New option --traversal-only (requires --target): prints one line "[OK] ..." or "[FAIL] ..." and exits 0 or 1. The other checks are unchanged, including the sensitive files (/.env, /en_CA/.env, /.git/config), which also answer 404 and are still probed hourly.
- Bugs fixed: none.
- Safeguards and edge cases: the rule is still verified: nginx-hardening.sh --update runs the test after installing the rules (section 12 bis, see its changelog). The local target still connects to 127.0.0.1 with the public host name, as before.
- Checks performed: python3 -m py_compile; test_app_health_check suite (see the report of the test run).
- Action required: none. The hourly report no longer contains the line "Traversal in the query string blocked by nginx". To see it: nginx-hardening.sh --update, or app-health-check.py --target local --traversal-only.

### 2.34.20261109.160000 - Works without root: notice at the start, detected values when the configuration is unreadable

- Title: app-health-check.py runs as an ordinary user and says at the start what it cannot see.
- Reason: request of the administrator on 2026-11-09: every program must work without root, show more as root, and say at the start what will not be available.
- Changes:
  - New function _non_root_notice() (apps/_config.py avis_non_root()): one line after "Configuration read" without root: nginx -T (public name), odoo.conf (database name), history kept in ~/.local/state instead of /var/lib/app-health-check, /etc/default not writable.
  - resolve_config_paths(): when the only configuration files are unreadable (600 root), the run no longer stops (exit 2 since 2.28): it warns and returns an empty list; main() then builds the values detected now in a temporary file (create_config(), its messages hidden by the new class contextlib_redirect_stdout_to_stderr), removed at the end (atexit).
  - lang/app-health-check.fr.po: the three new messages.
- Bugs fixed: symptom: "ERROR: configuration not readable without root ... (run with sudo)" and exit 2 for a plain user; diagnosis: the 2.28 guard against a false "not configured" stopped the whole run; fix: the run goes on with detected values and says so, the settings of the unreadable file stay ignored.
- Safeguards and edge cases: nothing is written in /etc/default or in the home folder; the temporary file is mode 600 and removed; no notice as root or with --help, --version, --changelog; when nothing can be detected the program stops with a clear message (exit 2).
- Checks performed: test_app_health_check (unreadable configuration, run as an ordinary user) [OK]; manual run as an ordinary user [OK].
- Action required: none.

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

### 1.189.20261110.193238 - Colours with a meaning only, disk latency statistics, websocket durations not coloured

- Title: the colours of the lines keep only their meaning; the latency block gives the distribution of the disk waits (min, mean, median, standard deviation, 95th and 99th percentiles); a websocket duration is no longer coloured.
- Reason: request of the administrator on 2026-11-10. (1) The duration of GET /websocket was coloured like a slow request (yellow from 3 s, red above 6 s), although a websocket is a connection kept open while a chat tab is open: a long duration is normal, not a problem, so no threshold is needed. (2) In the address column, the owner of the address block (RDAP organisation or network name, for an address that is not a known person) was yellow, which explained nothing; the wish is a white base colour, with colours only for what matters (known person, blocked address). (3) Statistics on the disk latency were missing from the summary.
- Changes: STYLES: "org", "reseau" (owner of the block), "ip" (country code and brackets) have no colour any more (plain white); "person", "team", "place", "server", "dns" and "banned" keep their colours. transfer_style() is no longer applied to the duration of a websocket (token(), condition "and sql"). LatencyMonitor: new deque self.disk_latency (DISK_LATENCY_KEEP = 20000 values), one value per sample of 30 s (wait per disk operation, all disks, weighted by the count of operations of each disk); new method disk_latency_stats() (min, mean, median, sample standard deviation, nearest-rank 95th and 99th percentiles, maximum); new line "Disk latency per operation" in the LATENCY block of lines() (Y key, summary, dashboard). statistics imported. lang/app-log-live.fr.po: fragments of the new line.
- Bugs fixed: symptom: a line "101 494 14.602" (websocket) showed its duration in yellow or red. Diagnosis: 1.141 applied the traffic light to every duration of a line; 1.145 and 1.171 excluded the websockets from the "slow" count, but not from the colouring. Fix: no colour for a websocket duration.
- Safeguards and edge cases: the Odoo requests (SQL time present) keep their traffic light; a websocket is still never a slow request (LONG_CONNECTION_RE unchanged). A sample with no disk operation in its interval is not counted. Before the first sample, the line is not displayed. The statistics are kept for the session (about 7 days at 30 s) and are exact, the values not being binned.
- Checks performed: python3 -m py_compile; test_app_log_live suite (see the report of the test run).
- Action required: none. Reading of the address column: the yellow text in the owner column is now plain; the legend of the program (startup) keeps the same wording, the colour of the owner being none.

### 1.188.20261109.234500 - Health without the probes of this server; slow static files said

- Title: the slow requests of the probes of this server no longer count in the health; the explanation says when slow requests are static files read from the disk.
- Reason: exports of DEV and PROD of 2026-11-09 23:35 with app-log-live.py 1.187 and apps/_advisor.py 1.15.
- Changes: health(): the indicator of the slow requests counts neither the cold cache (10 minutes after a start) nor the requests of this server (app-health-check.py, 127.0.0.1); analyze_slow(): line « N slow requests are static files or images with almost no SQL ... the cache of nginx serves them without Odoo » (apps/_advisor.py FILE_RE); lang/app-log-live.fr.po.
- Bugs fixed: symptom: DEV health « ⚠ à regarder » for 6 probes of app-health-check.py on a cold Odoo; fix: left out of the count (still listed).
- Safeguards and edge cases: the slow requests of visitors still count.
- Checks performed: test_app_log_live (slow requests, 13 tests) [OK].
- Action required: none.

### 1.187.20261109.233000 - Interruptions cut where Odoo answered again; memory recyclings counted since the start of Odoo

- Title: the interruptions seen by nginx are cut at each return of Odoo, and the recyclings of workers and of gevent are counted since the start of the running Odoo.
- Reason: analysis of the DEV and PROD exports of 2026-11-09 23:08 asked by the administrator.
- Changes: Stats.nginx_errors_times (each instant of an nginx error, 1000 last, kept by the copies of the statistics); health(): interruptions built from these instants (5 minutes without refusal = a new interruption); facts nginx_errors[].times for apps/_advisor.py; worker_memory(): odoo_start (start of the main Odoo process); memory_facts(): journal of the recyclings read since max(start of the period, start of Odoo).
- Bugs fixed:
  - symptom: PROD « interruption de 19:23:11 à 22:55:15 (3 h 32 min) » for five short restarts; diagnosis: the interruptions were built from the first and last instants of each message of the period; fix: from each instant.
  - symptom: PROD « Workers recyclés dès leur naissance ... 854 » while limit_memory_soft was 1637 MB, far above the 691 MB of a worker at rest; diagnosis: the 854 recyclings were those of the old limits (652 MB) before the restart at 22:55; fix: counted since the start of the running Odoo.
- Safeguards and edge cases: statistics saved before this version (without the instants) fall back to the first and last instants.
- Checks performed: OdooRuntime181 (odoo_start), test_advisor.test_115_analyse_dev_prod_20261109, manual check of the health on 5 refusals (3 interruptions).
- Action required: none.

### 1.186.20261109.221500 - Slow requests ended together without SQL: waiting for the disk

- Title: the explanation of the slow requests says when several of them ended together with almost no SQL (waiting for the disk).
- Reason: request of the administrator on 2026-11-09: the LXC container of Odoo 18 CE now has 32 GB; make the scripts set the right parameters so that nginx and PostgreSQL use the disk less (SATA disks, reads of 160 to 230 ms measured by host-perf-audit.py); check the buffers and the cache of the images in nginx-hardening.sh; a cause « waiting for the disk » in the analysis of app-log-live when several workers end together without SQL.
- Changes: analyze_slow(): line "N slow requests ended in the same 2 seconds (WHEN) with almost no SQL: waiting for the disk ..." (apps/_advisor.py ended_together()); lang/app-log-live.fr.po.
- Bugs fixed: none.
- Safeguards and edge cases: without apps/_advisor.py, nothing more is said.
- Checks performed: test_186_attente_du_disque [OK].
- Action required: none.

### 1.185.20261109.214000 - Slow requests in aligned columns, abnormal figures in colour

- Title: the slow requests of the health and of the summary are shown in aligned columns, the abnormal figures in colour.
- Reason: request of the administrator on 2026-11-09: "enligne l'information et rajoute de la couleur pour les chiffres anormaux" (slow requests of DEV).
- Changes: new method Stats.slow_row(): duration, date and time, SQL time, Python time, number of SQL queries, then the page and the client (of any length) last; duration orange, red from twice the threshold; SQL time when it takes 60 % of the request, Python time when it takes 80 %; number of SQL queries from SQL_HIGH (red from SQL_VERY_HIGH). analyze_slow(): pages grouped in columns (count, total, worst in colour, page padded to the longest of the list, then the cause), the share of SQL or Python that takes most of the time in orange, the counts of the addresses and of the cluster in colour; the fixed words of these lines are translated before the padding (the display translator kept the columns only partly); lang/app-log-live.fr.po: obsolete fragments "— SQL ", "% · Python ", "% (total " removed, " (total " added.
- Bugs fixed: none.
- Safeguards and edge cases: no colour when the output is not a terminal (color_code); the client and the page stay last, so a long name never shifts the columns.
- Checks performed: test_185_requetes_lentes_alignees_et_en_couleur (new), test_causes_des_requetes_lentes_dans_le_resume and test_requetes_lentes_surlignees_avec_leur_duree_et_slow (updated to the new layout), test_i18n: no new failure.
- Action required: none.

### 1.184.20261109.211500 - odoo.conf read the way Odoo reads it in the analysis

- Title: the analysis checks odoo.conf with apps/_odoo_conf_check.py (without starting Odoo).
- Reason: request of the administrator on 2026-11-09 (comment after a value refused by Odoo).
- Changes: gather_details(): details["odoo_conf_check"] (errors and warnings of apps/_odoo_conf_check.py check(), use_odoo=False, in the language of the display); used by apps/_advisor.py 1.13.
- Bugs fixed: none.
- Safeguards and edge cases: module missing or failing: no finding, the analysis goes on.
- Checks performed: test_odoo_conf_check [OK].
- Action required: none.

### 1.183.20261109.204500 - Limits of the live chat (gevent) read, restarts of gevent counted, memory available

- Title: the analysis reads limit_memory_soft_gevent / limit_memory_hard_gevent, counts the restarts of the gevent process and the memory available now.
- Reason: request of the administrator on 2026-11-09 (gevent limits and memory recommendations).
- Changes: ODOO_PERF_KEYS: limit_memory_soft_gevent, limit_memory_hard_gevent (shown in the environment, "-" when not set); memory_facts(): gevent_restarts (« Gevent virtual memory limit reached »), available_mb (MemAvailable); recycled no longer counts the gevent lines; used by apps/_advisor.py 1.12.
- Bugs fixed: none.
- Safeguards and edge cases: the journal is not read in the tests.
- Checks performed: OdooRuntime181 [OK].
- Action required: none.

### 1.182.20261109.194500 - Memory of the Odoo workers measured, recyclings counted

- Title: the analysis measures the virtual and real memory of the Odoo workers and counts the workers recycled for memory.
- Reason: report of the administrator on 2026-11-09 (PROD workers recycled in a loop, "virtual memory limit (691601408) reached").
- Changes: new function worker_memory() (median VmSize, VmRSS of the children of the main Odoo process, /proc/PID/status); memory_facts(): worker_vms_mb, worker_rss_mb, worker_overhead_mb, workers_measured, recycled and recycled_at_birth (journal of the service: "virtual memory limit", "exiting. request_count: 0,"); used by apps/_advisor.py 1.11.
- Bugs fixed: none in this program (the calculation was in apps/_advisor.py).
- Safeguards and edge cases: nothing measured without the processes (no root, service stopped): the advisor uses its usual values; the journal is not read in the tests.
- Checks performed: OdooRuntime181.test_182_memoire_des_workers [OK].
- Action required: none.

### 1.181.20261109.160000 - Odoo in memory versus odoo.conf, Odoo system parameters, server name in the journal names, nginx times

- Title: the analysis shows what the running Odoo really uses, the Odoo technical parameters themselves, and the journal files carry the name of the server.
- Reason: request of the administrator on 2026-11-09: [1] show the Odoo parameters directly instead of asking to check them in Settings > Technical; [3] show the changes of odoo.conf compared with what Odoo uses in memory; [4] the log file must contain the Linux server name; verification of the DEV export of 2026-11-09 (519 "pages by language" for 12 page views).
- Changes:
  - New constants PROC_ROOT (APP_LOG_LIVE_PROC_ROOT), CONF_SECRET_RE, ODOO_PARAM_DEFAULTS; new functions conf_options(), odoo_processes() (cgroup of the service, /proc/PID/cmdline and stat), odoo_runtime() (start of the main process, options of the command line, snapshot of odoo.conf kept at the first analysis after each start in odoo-conf-snapshots.json of the state folder, values changed since the start).
  - gather_details(): details["odoo_runtime"], details["params"] (ir_config_parameter mail.*, web.base.*, auth_signup.*, database.*, with the Odoo default when not set), details["backup_events"] (odoo-backup.service), details["service"]["name"].
  - environment_lines(): "Odoo running" line (start, processes, expected count, command line), changes of odoo.conf not in effect, "Odoo system parameters", PostgreSQL values with their unit (16384 8kB -> 128 MB), disks counted once per file system (/var/backups added), nginx times (rt=).
  - host_name(): journal files app-log-live-HOST-YYYY-MM-DD(.log|.html), header "server HOST", export export-ai-HOST-DATE.md; the purge also recognises the former names.
  - Stats: nginx_rt (rt= of nginx-hardening.sh 2.83), cut from the screen display with NGINX_TIMES_RE; the pages asked by this server itself (probes, warm-up) no longer counted in "Pages by language".
  - unit_events(): "Finished" and "Deactivated successfully" kept.
  - lang/app-log-live.fr.po: the new messages; doc/fr, doc/en 07-app-log-live.md.
  - nginx-tools-tests/test_app_log_live.py: HOTE_NOM, journal names, class OdooRuntime181.
- Bugs fixed: symptom: "Pages par langue (519 pages)" on DEV for 12 page views; diagnosis: the requests of app-health-check.py and of this server were counted in the languages (they were already left out of the visits since 1.179); fix: left out of the languages too.
- Safeguards and edge cases: keys holding a secret (pass, secret, token, key, private) are never shown nor kept; without root or without systemd nothing is shown (empty result); a file modified after the start without a snapshot is said "values in effect not known" rather than guessed; the snapshot file is mode 600.
- Checks performed: OdooRuntime181, test_advisor, catalogue tests [OK]; full suite by the testeur agent.
- Action required: none (the new journal names start at the next day; the former files are still purged).

### 1.180.20261109.110500 - Findings checked by an administrator (--ack), Odoo device log

- Title: what an administrator has already checked is listed apart; the analysis says whose Odoo session runs from a looping or suspicious address.
- Reason: request of the administrator on 2026-11-09: the 3 198 calls from a mobile network in Congo were a volunteer of the team (a loop of the Odoo web client); "ce qui est important serait ce qui n'a pas été vérifié par un admin Odoo".
- Changes:
  - New options --ack CODE (repeatable), --ack-note TEXT, --ack-days N (configuration key ACK_DAYS, default ACK_DAYS_DEFAULT = 30), --ack-list, --unack CODE; new function acknowledge(): the code is found in the histories of the analysis (advisor-history.json and advisor-history-advise.json), the entry is written to acknowledged.json (state folder, mode 600) with the note, the user (SUDO_USER), the date, the end date and the count of the finding.
  - advise(): the findings checked are split from the others (apps/_advisor.py split_acknowledged()) after the history is recorded, and given to render(); the export shows them too.
  - gather_details(): details["devices"]: the sessions of res_device_log (Odoo 17+, read only) for the addresses of the loops and of the bans proposed: login, name, internal or portal, platform, browser, last activity, revoked.
  - doc/fr and doc/en app-log-live.conf.example: ACK_DAYS and the new command-line options; lang/app-log-live.fr.po: the new messages; doc/fr, doc/en 07-app-log-live.md: "Findings checked by an administrator". nginx-tools-tests/test_app_log_live.py: class AppLogLive180.
- Bugs fixed: none.
- Safeguards and edge cases: an unknown code is refused (exit 1) and nothing is written; a check ends after --ack-days; the finding comes back when its count more than doubles; the history keeps every finding (trends unchanged); without res_device_log (Odoo 16 and older) the analysis is unchanged; the device query is read only and limited to 50 addresses.
- Checks performed: AppLogLive180, test_advisor (64 tests), test_config_defaut, test_cles_modeles, export test [OK].
- Action required: after the next analysis, mark the loop of the volunteer: sudo app-log-live.py --ack CODE --ack-note "bénévole, boucle du client web" (CODE: the 6 characters after the title of the finding).

### 1.179.20261109.100500 - Verification of the DEV and PROD exports: visits, --advise, service journal, environment, configuration keys

- Title: the first two daily exports (DEV and PROD, 2026-11-09) were checked line by line; what was not true is corrected, the export says more about the server, and every setting option has its configuration key.
- Reason: request of the administrator on 2026-11-09: continue the improvements, add a configuration key for --buffer and make sure that every option of every program is also in /etc/default; the two exports were sent for verification.
- Changes:
  - Stats.ajouter(): a page asked by this server (Stats.server, loopback) is no longer a site visit (pages, pages_per_ip, visits).
  - LatencyMonitor.batch (set for --advise) and verdict(): with --advise, "disks not measured with --advise" instead of "let it run a few hours".
  - unit_events(): new argument odoo_lines and ODOO_JOURNAL_LINE_RE: the lines written by Odoo in the journal of its service are no longer starts or stops; gather_details() hands them over as details["service"]["odoo_events"] (timeline).
  - Stats.conflict_times and push_instants; advisor_facts()["push_after_conflict"].
  - memory_facts(since, service): "other_mb" (MemTotal - MemAvailable minus MemoryCurrent of the Odoo service), as nginx-hardening.sh step 6.
  - gather_details(): nginx access logs read up to ADVISE_NGINX_BYTES = 200 MB per file with --advise (30 MB before).
  - export_ai(): new section "Environment of the server" (environment_lines(): Odoo version, odoo.conf, memory of the server and of its container, Odoo service MemoryCurrent / MemoryPeak / MemoryMax / NRestarts, PostgreSQL settings, timers of the suite, free space of /, /var/log and /var/lib/postgresql, load and uptime).
  - SCHEMA_CONFIG: new keys COUNTRY, EXCLUDE_COUNTRY, UTC, NO_HOSTNAME, NO_HTML_JOURNAL.
  - doc/fr and doc/en app-log-live.conf.example: BUFFER, COUNTRY, DISPLAY_HOST, EXCLUDE_COUNTRY, HIDE_USER_AGENT, NO_HOSTNAME, NO_HTML_JOURNAL, NO_SITEMAP, REQUEST_LENGTH, SITEMAP, STATUS_EVERY, UTC (alphabetical order), a comment for LOG_MERGE, and the command-line options --apply, --config-merge, --follow, --grep, --log-chk-sitemap, --no-pager, --since, --until.
  - lang/app-log-live.fr.po: the new messages and the missing translation of --no-html-journal. doc/fr, doc/en 07-app-log-live.md: "What 1.179 changes". nginx-tools-tests/test_app_log_live.py: class AppLogLive179 (5 tests), export test checks the new section.
- Bugs fixed:
  - Symptom (DEV): 10 visitors, 49.7 pages per visitor, "/" x176. Diagnosis: the requests of app-health-check.py and of this server were counted as visits. Fix: excluded.
  - Symptom (PROD): "0 of them in the 10 minutes after a start of Odoo (2 starts in the window)" while Odoo had not restarted. Diagnosis: journalctl -g "Started|Starting" also matched the auto_backup lines of Odoo. Fix: Odoo lines apart.
  - Symptom (PROD): consistency check "[ATTN] account forms: 24 counted, 14 found in the access logs". Diagnosis: only the last 30 MB of each access log was read. Fix: 200 MB with --advise.
  - Symptom (DEV and PROD): "not enough data yet ... (let it run a few hours)" after --advise. Diagnosis: the disks are sampled live only. Fix: verdict of its own.
- Safeguards and edge cases: a page asked by this server is still a request (counts, URLs, errors); environment_lines() never fails (a value that cannot be read is left out) and runs no external command in the tests; the configuration keys follow the existing types (comma lists, booleans).
- Checks performed: AppLogLive179, AppLogLive178, test_178_export_ai_avec_advise, test_advisor (61 tests), test_config_defaut and test_cles_modeles (now without failure), test_nginx_hardening.SuggestionMemoire282 [OK]; whole suite: see the pull request.
- Action required: update the suite. For the daily check: sudo app-log-live.py --advise 1 --export-ai.

### 1.178.20261109.081127 - Night report review: true figures, push duplicates apart, full country names, --export-ai

- Title: the summary and the analysis of the night of 2026-11-09 are corrected where they did not tell the truth, and a new option writes one file to send every day for verification.
- Reason: review on 2026-11-09 of the dashboard of the night (v1.176) and of the analysis (z key): health "problem" for harmless errors, means of 20 s with a median of 0.02 s, "PostgreSQL 0 %" while the slow pages were 99 % SQL, "Banned addresses seen: 0" after two bans, an analysis window that started after the events it showed, failed e-mails without date, subject nor recipients. The administrator also asked for the full name of the countries ("CD" -> "CD (République démocratique du Congo)") and for an option `--export-ai` to send the summary and the analysis every day.
- Changes:
  - Stats.ajouter() / LatencyMonitor: a websocket or longpolling line is no longer given to LATENCY.request() (new condition on LONG_CONNECTION_RE).
  - New PUSH_DUPLICATE_RE, UNIQUE_VIOLATION_RE, PUSH_DUPLICATE_WARNING_RE and benign_reason(): the "bad query" line is classified by the line that follows it (retried conflict or push subscription already registered); release_deferred() receives the text of that line; Formatting.format_value() writes the reason of a push duplicate.
  - Stats: push_duplicates, push_duplicate_warnings, push_duplicates_time (counted apart, never in odoo_errors nor in the failed e-mails); new health indicator "Push subscriptions already registered (harmless)"; since() gives the difference.
  - StatusBar.observe(): new argument benign, an error without severity is no longer counted in "Odoo errors" (the status bar said 38 while the summary said 6).
  - Stats.banned_during() and the summary line "Addresses banned by fail2ban during the period"; Stats.who_country() adds the full country of an unknown address in the most active addresses, the suspicious and account-form addresses, the bans and the addresses to ban.
  - country_label() and the new shared module apps/_countries.py: "Visitors' countries" and "Requests by name" show "US (États-Unis) 272", "[CD (République démocratique du Congo)]".
  - Stats.ip_url / ip_url_codes (at most IP_URL_MAX = 200000 pairs) and HOT_PAIR_MIN = 300, HOT_PAIR_SHARE = 0.3: advisor_facts() hands over "hot_pairs" (one address asking the same page again and again).
  - Stats.odoo_errors_raw (one raw line per grouped error), Stats.first_any (oldest line of any kind).
  - advisor_facts(): "start" is the oldest line read (nginx error log and Odoo log included), plus "requests_start", "end", "push_duplicates", "push_duplicate_warnings", "push_times", "hot_pairs", "banned_during", "known_ips", the raw example of each Odoo error, and "who" with the country.
  - gather_details(): odoo.conf read for every analysis (memory risk), memory_facts() (cgroup memory.max or memory.limit_in_bytes, memory.events, kernel messages of the OOM killer through journalctl -k), each failed e-mail (odoo_db.courriels_en_echec: date, subject, recipients, full reason), the outgoing servers with id, name, FROM filter and state, the portal accounts created in the window (date, domain of the login, sign-ins since), the scheduled actions whose last run was around the slow requests.
  - advise(): a line "Oldest line read ... first request read ..." when they are more than one hour apart.
  - New option --export-ai [FILE] and configuration key EXPORT_AI (export_ai_path()); export_ai() writes the summary, the analysis, the timeline (apps/_advisor.py timeline()), consistency_checks() and the main counters in JSON, Markdown without colors, mode 600, pseudonyms when --anonymize is active; default file export-ai-YYYYMMDD-HHMMSS.md in the state folder.
  - New constant CGROUP_ROOT (APP_LOG_LIVE_CGROUP_ROOT for the tests).
  - lang/app-log-live.fr.po: the new messages. doc/fr/07-app-log-live.md, doc/en/07-app-log-live.md: "Daily check: --export-ai" and "What 1.178 changes". doc/fr/app-log-live.conf.example, doc/en/app-log-live.conf.example: EXPORT_AI. nginx-tools-tests/test_app_log_live.py: class AppLogLive178 (6 tests) and test_178_export_ai_avec_advise.
- Bugs fixed:
  - Symptom: "Requests while the disk was busy: 3555 (mean 20.60 s) · calm: 12818 (mean 19.01 s)" with a median of 0.02 s, and "time spent in PostgreSQL 0 %, in Python 100 %" with an "SQL %" column at 0 every hour. Diagnosis: the Odoo line of a websocket carries its whole duration (hours of Python time) and was counted as one request; a few of them made the means and the shares meaningless. Fix: the long connections are not counted in the latency (as in the slow requests since 1.171).
  - Symptom: health "problem" because of "ERROR odoo.sql_db x5: bad query: INSERT INTO mail_push_device", and an analysis that called it "concurrent update retried by Odoo". Diagnosis: it is a unique violation (constraint mail_push_device_endpoint_unique) when a browser subscribes again to the push notifications; Odoo does not retry it and nothing is lost; only "could not serialize access" was recognised. Fix: benign_reason() recognises the duplicate; counted apart; status bar and summary agree.
  - Symptom: "Banned addresses seen: 0" while fail2ban had banned two of the addresses of the night (at 05:58 and 06:53). Diagnosis: since 1.171 this line counts the requests of addresses already banned when they asked; the bans of the period were nowhere. Fix: new line of the addresses banned during the period.
  - Symptom: analysis "since 2026-11-07 23:39:33" showing nginx errors from 06:53 to 15:16 the same day. Diagnosis: the start of the window was the first REQUEST read; the nginx error log was read further back. Fix: the start is the oldest line read; the first request is said apart.
  - Symptom: "Formulaires: 18 sur 18 de personnes déjà connues" with an amazonaws.com host in the list. Diagnosis: apps/_advisor.py took any address with a name for a known person. Fix: known_ips (people signed in, team, places) handed over.
- Safeguards and edge cases: a websocket still counts in the requests and the URLs; a "bad query" on mail_push_device followed by another error (syntax) stays an error; a unique violation on another table stays an error; the (address, page) pairs are bounded (IP_URL_MAX) and the long connections are not counted; the country is never added for the people, the team, the places or this server; country_label() gives the code alone without apps/_countries.py; memory_facts() never fails (no cgroup file, no root: None and []); journalctl -k is not run in the tests (NGINX_TOOLS_TESTS); --export-ai with "no" or "off" writes nothing, without a folder writable the current folder is used, an unwritable file is said in one line and the analysis is kept; the export is written with the pseudonyms of the screen when --anonymize is active.
- Checks performed: test_app_log_live, test_app_log_live_ban, test_app_log_live_fail2ban and test_advisor (361 tests): [OK] except 9 tests that fail the same way on main in the test sandbox (pseudo-terminal and Ctrl-C prompt: test_157, test_120, Ctrl-C summary, menus, legend, columns, addresses to ban); test_statistiques_des_visites_du_site updated for the full country names; test_i18n, test_docs, test_conventions, test_cles_modeles, test_config_defaut: only the failures already present on main; ruff (E9, F, py38): only the warning already present on main.
- Action required: update the suite, then quit the running dashboards (Ctrl-C) and start them again. For the daily check: sudo app-log-live.py --advise 1 --export-ai, then send the file written (its path is printed at the end).

### 1.177.20261107.234906 - Analysis: translations read again after an update of the suite

- Title: a dashboard started before an update shows the new messages of the analysis in French, and says that it runs the old version.
- Reason: the report of the z key on 2026-11-07 (title "app-log-live.py v1.175") mixed English and French: "Sign-up and password reset forms: 12 requêtes, mostly depuis people already known", "2 people registered several times...", "Cause probable : the registrations were made WITH a visitor...". The administrator asked for the missing translations.
- Changes: new constant SUPPLEMENTARY_CATALOGUES (the list passed to demarrer()), new functions catalogues_mtime(), refresh_translations() and version_on_disk(), new global CATALOGUES_READ_AT. advise(): calls refresh_translations() right after loading apps/_advisor.py, and adds one line under the title when the program on the disk has another version. lang/app-log-live.fr.po: one message. nginx-tools-tests/test_app_log_live.py: class AppLogLive177 (2 tests).
- Bugs fixed:
  - Symptom: messages of the analysis in English, or translated word by word ("depuis", "adresse", "requêtes" inside English sentences).
  - Diagnosis: no translation was missing: lang/_advisor.fr.po has all these messages since apps/_advisor.py 1.6 (app-log-live.py 1.176). The dashboard had been started with 1.175 and kept running during the update: apps/_advisor.py is read again from the disk at every z, but the catalogues were read only at start. The new messages of 1.6 were therefore unknown to the old translator, which only replaced the words it knew. Proof: these exact messages come out in French with the catalogues of main.
  - Fix: when a lang/*.po file is more recent than its reading, the translator is built again (global TR and I18N.tr) before the analysis.
- Safeguards and edge cases: any problem while building the translator keeps the current one; no catalogue changed -> nothing is read again (a stat of the lang/*.po files per z only); the modification time is taken BEFORE the reading, so a file written during the reading is read again next time; the code of the program itself is never reloaded (only the warning line asks to start it again); without apps/_i18n.py nothing changes.
- Checks performed: test_app_log_live.AppLogLive177 (2 tests) [OK]; the other tests: see the pull request.
- Action required: update the suite, then quit the running dashboards (Ctrl-C) and start them again once. For the dashboard that showed the report of 2026-11-07, restarting it is enough to have the analysis in French, even before this update.

### 1.176.20261106.110050 - Analysis: facts about the addresses of this server

- Title: the analysis knows which addresses are the ones of this server.
- Reason: review on 2026-11-06 of the report of one day of the administrator (see apps/_advisor.py 1.6).
- Changes: app-log-live.py hands over facts["server_ips"] (Stats.server) to the analysis. nginx-tools-tests/test_advisor.py: three tests.
- Bugs fixed: none in this program (see apps/_advisor.py 1.6).
- Safeguards and edge cases: loopback addresses are recognised by the analysis even when the list is empty.
- Checks performed: test_advisor (44 tests), test_i18n (only the failures already present on main).
- Action required: none.

### 1.175.20261106.104955 - --advise --days N analyses N days; the analysed period is said

- Title: `--advise` without a value uses the window of `--days` when it is given; the program prints the period it analyses.
- Reason: report of the administrator on 2026-11-06: "J'ai demande de verifier sur une journee seulement et c'est long" with `app-log-live.py --advise --days 1`, which read the logs since 2026-10-23.
- Changes:
  - app-log-live.py: --advise const -1 (no value): window = --days if greater than 0, otherwise 14 days (ADVISE_DAYS_DEFAULT); new line "--advise: period analysed from DATE (N days; ...)" before the reading; help text.
  - lang/app-log-live.fr.po, doc/fr/07-app-log-live.md, doc/en/07-app-log-live.md: the rule. nginx-tools-tests/test_app_log_live.py: class AppLogLive175.
- Bugs fixed:
  - Symptom: `--advise --days 1` read 14 days of logs (about 40 minutes). Diagnosis: the value of --advise is its own argument (14 days by default); --days only sets the sign-in history, so the two options were independent and the user thought --days limited the analysis. Fix: --advise alone takes the value of --days.
- Safeguards and edge cases: `--advise 7 --days 1` keeps 7 days for the analysis (the explicit value wins); `--since` still chooses another window; --days 0 (all, the default) keeps the 14 days; the limit of 366 days is unchanged; the DAYS of the configuration file counts like --days.
- Checks performed: AppLogLive175 (3 tests), test_i18n and test_docs (only the failures already present on main).
- Action required: none. For a quick check of one day: `app-log-live.py --advise 1`.

### 1.174.20261106.095903 - Password reset and sign-up forms in red only from the 4th request of an address

- Title: /web/reset_password and /web/signup are shown in red reverse video only when the same address asks them more than three times.
- Reason: request of the administrator on 2026-11-06: "/web/reset_password affiche en inverse video en rouge, mais ce n'est pas encore une erreur, mais seulement si on retrouve cela plus que trois fois".
- Changes:
  - app-log-live.py: ACCOUNT_FORM_ALERT_N = 3; Formatting.account_form_repeated(), account_count and account_pending (the live line is formatted just before it is counted by Stats, the lines shown again by the f and P keys are already counted); follow() connects the counter of Stats.account_ips to both formatters.
  - doc/fr/07-app-log-live.md, doc/en/07-app-log-live.md: the rule. nginx-tools-tests/test_app_log_live.py: class AppLogLive174.
- Bugs fixed: none.
- Safeguards and edge cases: the count is per address (a robot that follows the link of each page is red from its 4th request, the summary "Account forms" still counts them all); this server's own addresses are never counted; without a counter (a Formatting used alone) the form stays red as before.
- Checks performed: AppLogLive174 (2 tests), AppLogLive173, test_i18n (only the failures already present on main), test_docs.
- Action required: none.

### 1.173.20261106.095017 - Security tests of this server are not 404 errors

- Title: the 404 answers of the hourly security tests of app-health-check.py (launched by web-monitor.py) are no longer counted as errors, nor tagged for sitemap.xml.
- Reason: question of the administrator on 2026-11-06: "pourquoi les tests a toutes les heures generent des erreurs 404", with the line "ce serveur 404 548 GET /some/page?file=../conf/conf.php [pas dans sitemap.xml]".
- Changes:
  - app-log-live.py: local_probe() (suspicious URL asked from the loopback address); Stats.ajouter() counts it in the probes only (not in the 4xx errors, the 404 of the sitemap, nor the problem addresses); StatusBar.observe() gives it no penalty (health, 4xx counter); the line shows [probe of this server] (French: [sonde de ce serveur]) instead of the sitemap tag.
  - lang/app-log-live.fr.po: the new tag. nginx-tools-tests/test_app_log_live.py: class AppLogLive173.
- Bugs fixed:
  - Symptom: every hour the dashboard counted one more 404 "not in sitemap.xml" (and the analysis could mention it). Diagnosis: app-health-check.py asks /some/page?file=../conf/conf.php, /.env, /en_CA/.env and /.git/config to check that nginx refuses them (404 of 548 bytes, expected); the loopback address was only excluded from the suspicious addresses, not from the error counters. Fix: same exclusion for the error counters, the health and the line tag.
- Safeguards and edge cases: only a SUSPICIOUS URL from the loopback address is concerned: a real broken link requested by this server (404 on a normal page) stays counted; the same request from an external address stays counted and tagged as before; a 5xx on such a URL is still counted.
- Checks performed: AppLogLive173 (3 tests), AppLogLive172, test_i18n (only the failures already present on main).
- Action required: none.

### 1.172.20261106.094106 - Analysis (z): the program checks who asked, who answered, and the registrations in the database

- Title: for the 404 pages, the analysis reads itself in the access log and in the Odoo database what the administrator had to look for by hand.
- Reason: request of the administrator on 2026-11-06: "avec analyse des problemes soulevés (z), peux-tu rajouter plus de validation (...) le programme peut le faire lui-même afin de donner un meilleur diagnostique", after an investigation of the 404 on /event/<id>/registration/success done with grep, awk and curl.
- Changes:
  - app-log-live.py: the details of the analysis read, for the confirmation links in 404, the registration_ids in the database (read only): registrations found, without visitor recorded (visitor_id empty), people registered several times for the same event (details["registrations"]).
  - apps/_advisor.py 1.5: nginx_details() also keeps the robots and the browsers (with their addresses), the queries and the size of the 4xx answers; origin_lines() adds to every 404 finding: who answered (page of nginx of about 150 bytes: a rule of nginx; page of several KB: Odoo), who asked (robots, link previews, tools, or browsers from N addresses) and the addresses asked again by browsers; registration_success(): finding "registration-404" (information when only robots and link previews, "to look at" when browsers, with the cause and the corrections).
  - lang/_advisor.fr.po: the new sentences. nginx-tools-tests/test_advisor.py: two tests; test_app_log_live.py: class AppLogLive172.
- Bugs fixed: none.
- Safeguards and edge cases: the SQL queries are SELECT only, and PostgreSQL itself forces the read-only transaction; at most 200 registration numbers; without database access the lines on registrations are simply not shown; a finding keeps its previous form when the access log has no detail for the page.
- Checks performed: test_advisor (41 tests), AppLogLive172, test_i18n (only the failures already present on main).
- Action required: none. The corrections proposed for the registration pages (thank-you page instead of the 404) are for rlq-odoo-addons, on request.

### 1.171.20261106.083524 - [BANNIE PLUS TARD], websocket never slow, pages asked again with their parameters

- Title: a request made before the ban of its address is labelled [BANNIE PLUS TARD] (it went through); the websocket of a merged line is never a slow request; the analysis asks a page again with the parameters that were sent.
- Reason: request of the administrator on 2026-11-06: lines marked [BANNIE] with answers 200, 303 and 304 (a logged-in user), and review of the analysis of the night.
- Changes:
  - app-log-live.py: Bans.ban_after(); compose() compares the instant of the request with the fail2ban journal: banned only later -> [BANNIE PLUS TARD] (Odoo lines: [banned later: jail HH:MM]), and the line is no longer counted as a request of a banned address; line_duration() returns None for /websocket and /longpolling; NO_PROBE_RE and sent_url in the page re-check of the analysis.
  - lang/app-log-live.fr.po: "[BANNED LATER]".
  - nginx-tools-tests/test_app_log_live.py: class AppLogLive171.
- Bugs fixed:
  - Symptom: [BANNIE] on lines answered 200, 303, 304. Diagnosis: the label was the state of the ban when the line is displayed (history read at start included), not the state when the request was made. Fix: the ban time of the fail2ban journal is compared with the time of the request. Bans of the firewall and of CrowdSec have no time in their lists: they keep [BANNIE].
  - Symptom: "slow requests: /websocket x10, 4911 s" in the analysis. Diagnosis: since 1.169 the duration of a merged line was taken without the long connection test of 1.145. Fix: the test is done first.
  - Symptom: "Response of the site now: 303" for a page that answered 404 with its filters. Diagnosis: the page was asked again without its query string. Fix: it is asked with the first query string seen.
  - Symptom: an Odoo error (TypeError, 500) written by the analysis itself on /registration/success. Diagnosis: the page was asked again without registration_ids. Fix: /registration/success and /my_tickets are not asked again.
- Safeguards and edge cases: without a readable fail2ban journal the label is unchanged; a ban before the request (within 24 h) is still [BANNIE]; the 4xx page is asked again only on the local nginx.
- Checks performed: AppLogLive171 (4 tests), AppLogLive170, test_advisor, test_i18n.
- Action required: none. To check one address: sudo fail2ban-client banned | grep ADDRESS and sudo grep ADDRESS /var/log/fail2ban.log.

### 1.170.20261105.130658 - Menu switches for every option that can change while running

- Title: new menu keys J (--log-merge), B (--status-header), C (--truncate), O (--utc), Q (--slow), Z (--status-every), K (--no-ban-prompt), y (--no-sitemap); the menu lists the options set at startup only.
- Reason: request of the administrator on 2026-11-05: "une option bascule qui fera LOG_MERGE et hide/show user agent. S'assurer qu'il y ait des bascules pour toutes les options possibles".
- Changes:
  - app-log-live.py: MENU_KEYS (J B C O Q Z K y); key() handles logmerge, statusheader, truncate, utc, slow, statusevery, banprompt, sitemap; menu() shows each switch with its current value, keeps u (--hide-user-agent) and x (--log-nginx), and adds the line "Set at startup only".
  - config_values(): the W key also saves LOG_MERGE, LOG_NGINX, STATUS_HEADER, SLOW, STATUS_EVERY, NO_BAN_PROMPT, DISPLAY_HOST and NO_SITEMAP when they changed.
  - lang/app-log-live.fr.po: French texts of the new lines.
  - doc/fr/07-app-log-live.md, doc/en/07-app-log-live.md: the new keys.
  - nginx-tools-tests/test_app_log_live.py: class AppLogLive170.
  - nginx-tools-tests/test_config_commune.py: test_touche_c_dans_le_menu checks W (save) and C (--truncate); it still looked for the save under C.
- Bugs fixed: none.
- Safeguards and edge cases: J turned off shows at once the nginx lines waiting for their Odoo partner (nothing is lost); J warns when --log-nginx (key x) is off; Q and Z ask a number and refuse a value out of range (Q 0 to 3600, Z -1 to 100000); y turned on again reads the sitemap.xml given at startup, or the default one, in the background; B shows the column labels again.
- Checks performed: run-all.sh (mawk and gawk): no new failure, only the failures already present on main; AppLogLive170 (5 tests), test_config_commune, test_nginx_uri.
- Action required: none.

### 1.169.20261105.083208 - Dashboard: Odoo times of merged lines counted, cold cache and probes apart, interruptions, stopped monitoring

- Title: the dashboard counts the Odoo times of the lines merged by --log-merge, sets apart the slow requests after a start of Odoo and the probes of this server, groups the nginx upstream errors into interruptions and says when web-monitor.py has stopped.
- Reason: request of the administrator on 2026-11-05: improvements seen in a dashboard of 10 h 49 of the production server (app-log-live.py 1.166).
- Changes:
  - New functions line_detail() and line_duration(): the Odoo times of a merged line (L.odoo_times); used by Stats.ajouter() (slow requests, latency) and StatusBar.observe() (slow, most SQL queries).
  - New function service_started_at() (systemctl show ActiveEnterTimestamp, date -d, read again every 60 s) and Stats.service_start (set by follow()).
  - Stats.health(): slow requests of the 10 minutes after the start of Odoo shown and left out of the health level; probes of this server named; upstream errors grouped into interruptions (5 minutes apart), level "to look at" for one short interruption, "problem" for several or one of more than 15 minutes; new indicator "Automatic monitoring (web-monitor.py): last run N h ago" (Stats.reco_age_h) beyond 48 hours.
  - analyze_slow(): the state of the server now is shown only when the latest slow request is less than 5 minutes old.
  - Account forms, suspicious requests: "requests: N · addresses: K" instead of "request(s)", "address(es)" and the French "de" in the English code.
  - lang/app-log-live.fr.po (10 entries, one stale removed); doc/fr and doc/en 07-app-log-live.md; tests: class AppLogLive169 (5 tests).
- Bugs fixed:
  - Symptom: "Odoo requests: 67" in the latency and 3 slow requests for 2,603 requests in 10 hours, with --log-merge. Diagnosis: a merged line has the text of the nginx line; Stats.ajouter() and StatusBar.observe() read the duration in the text (request_duration, request_detail), only the display read L.odoo_times. Fix: line_detail() and line_duration().
  - Symptom: "Python alone is to blame: right now ... probable causes: disk too slow" for requests of the evening before, with "disk wait 0 %". Diagnosis: the state of the server at the time of the display was used to explain requests of hours before. Fix: only for requests of the last 5 minutes.
  - Symptom: the health "problem" for one restart of Odoo of 5 minutes (26 lines of the nginx error log); 2 of the 3 slow requests were the probes of app-health-check.py right after that restart. Fix: interruptions and cold cache.
  - Symptom: "4 request(s) from 1 address(es)" and "51 de 4 adresses". Fix: counts with a colon.
- Safeguards and edge cases: a line without any time stays without duration (as before); without systemctl or without a start time, nothing is left out of the health; the monitoring warning appears only when the file of web-monitor.py exists (a server without web-monitor.py is not warned).
- Checks performed: AppLogLive169 (5 tests); the tests of the merge (AppLogLive123, 143, 153), of the dashboard and of --advise.
- Action required from the user: none. On the server: the last web-monitor.py run is 82 h old: systemctl list-timers 'web-monitor*' to see why.

### 1.168.20261105.081634 - --advise shows its progress

- Title: --advise shows where the reading of the window is, then each step of the analysis.
- Reason: request of the administrator on 2026-11-05: with app-log-live.py --advise nothing is shown for several minutes.
- Changes: new class AdviseProgress (line(), done(), step()) and function clock_span(); follow() creates it when the output is muted and gives it each line read; the end of the reading and each step of advise() and gather_details() (names of the addresses, Odoo tracebacks, nginx access logs, service journal and odoo.conf, Odoo database, answer of the site, rules and history) are shown with the time since the start; lang/app-log-live.fr.po: 11 entries; doc/fr and doc/en 07-app-log-live.md; tests: class AppLogLive168 (3 tests).
- Bugs fixed: none.
- Safeguards and edge cases: the progress goes to the error output (the analysis on the standard output stays clean); on a terminal one line is rewritten at most once a second; without a terminal (log file, mail of a scheduled task) one line every 30 s; the percentage follows the date of the lines read within the window (--since / --until included), the time left is shown only after 5 s and between 2 and 100 %; the z key of the live stream is unchanged.
- Checks performed: AppLogLive168; a synthetic run of --advise (steps in order).
- Action required from the user: none.

### 1.167.20261105.071311 - --advise checks the facts itself, true counts, --apply for the corrections

- Title: the analysis of --advise and of the z key reads the details of each problem itself (odoo.conf, database, service journal, answer of the site), the counts of the dashboard are true, and --apply offers the corrections one by one.
- Reason: request of the administrator on 2026-11-05, after the first --advise run on 14 days of the production server: check that the output is correct and true; check the advice by itself (for example "check workers, limit_time_cpu and limit_time_real in odoo.conf"); an option to ask to apply some corrections (addresses to ban, failed e-mails...).
- Changes:
  - Stats.ajouter(): the lines of the nginx error log (database "nginx") are counted in the new counters nginx_errors and nginx_errors_time (COUNTERS, snapshot), never in odoo_errors nor in mails. New health indicator "Odoo unreachable from nginx (upstream errors)" (UPSTREAM_ERROR_RE) with the first and last time; level 8 line "nginx errors (error log)".
  - advisor_facts(): nginx_errors, http_errors5 (time, code, URL, address of each 5xx), account_urls, site_hosts (host of the sitemap), names of the addresses of the 5xx and of the bans.
  - New closures gather_details(), record_of(), db_rows(), odoo_bases() and apply_corrections(); new functions unit_events() (starts and stops of the service: journalctl -u -o short-unix -g), unit_state() (systemctl show), odoo_perf_settings() (workers and limits of odoo.conf, processors of the cpuset, MemTotal); EVENT_PATH_ID_RE, PRODUCT_PATH_ID_RE.
  - gather_details(): Odoo tracebacks (logfile or journal around the time), the exceptions of every occurrence of "Exception during request handling" (journalctl -g on the window), the traceback of each 5xx page (at most 5 pages, the last 3 answers), nginx referers and methods (pages answering 404 and account forms), the mail queue of each database (_odoo_db.courriels, outgoing servers), the write date of the VAPID key, the sign-up setting and the portal accounts created, the record of each page answering 404 (event_event, product_template, website_page and a similar page), the redirects already defined (website_rewrite), and the answer of the site now (local_request to 127.0.0.1:443 with the host of the site). PostgreSQL is read in read-only transactions.
  - New option --apply (with --advise; refused without it): after the analysis, one question per correction: ban each address through nginx-log-audit.sh --ban IP --reason (investigation, white list, score threshold 3, its own confirmation), open odoo-mail-retry.py --days N, run odoo-warmup.py. The analysis shows "correction offered by --apply" under each finding that has one.
  - apps/_advisor.py 1.3 (see its section); lang/app-log-live.fr.po and lang/_advisor.fr.po; doc/fr and doc/en 07-app-log-live.md; tests.
- Bugs fixed:
  - Symptom: "Failed e-mails: 40" on the dashboard and in the analysis, while Odoo had not failed to send them. Diagnosis: the nginx error lines "connect() failed (111: Connection refused) while connecting to upstream" (Odoo restarting) have the level ERROR and match MAIL_ERROR_RE ("Connection refused"): Stats.ajouter() counted them as failed e-mails and as Odoo errors. Fix: the nginx error lines are counted apart; the analysis takes the number of failed e-mails from the database.
  - Symptom: the same nginx message shown as three "Odoo ERROR" findings, "an error of Odoo not yet known". Diagnosis: same cause; one key per client and request. Fix: rule_nginx_upstream groups them and links them to the restart of the service.
  - Symptom: "Linked from other sites: https://rencontres-linux.quebec/..." for the site's own pages. Diagnosis: the log format writes host="$host" with quotes, the quotes stayed in the host compared, and www was not ignored. Fix: see apps/_advisor.py 1.3.
  - Symptom: "25 answers 404" while the codes said 404 x25, 403 x3 and the redirects 301 were listed as errors; the same page counted once per query string. Fix: the title counts the 404 read by nginx, the query strings of a page are grouped and the 3xx are shown apart.
  - Symptom: the cause of "Exception during request handling" was drawn from the LAST occurrence only, the 5xx of the same page with different query strings were separate findings, a vulnerability scanner (search=zqzz, tags=stfD) was reported as an Odoo bug to fix. Fix: see apps/_advisor.py 1.3.
- Safeguards and edge cases: everything gathered is read-only (PostgreSQL read-only transactions, logs read, one GET per page answering 404, at most 10, 6 s each; never during the tests); without root (odoo.conf, database or journal unreadable) the analysis says what was not checked instead of assuming defaults; at most 3 databases; --apply needs a terminal and asks for each correction (no unattended mode, no bulk ban); odoo.conf is never modified; bans keep the rules of the suite (nginx-log-audit.sh checks the white list and the score, CDN relays are never proposed).
- Checks performed: test_167_erreurs_nginx_hors_odoo_et_hors_courriels, test_167_apply_bannit_avec_nginx_log_audit, test_167_apply_sans_advise_refuse; test_advisor (class Version167, 13 tests); a synthetic journal like the production one (nginx upstream errors during a restart, VAPID tracebacks, 500 on a form and on a fuzzed search, 404 with referers) checked line by line.
- Action required from the user: none. Suggested: sudo app-log-live.py --advise --apply (sudo: odoo.conf, the database and the service journal are read).

### 1.166.20261104.204925 - --advise about 15 times faster, with the lowest priority

- Title: --advise reads the window about 15 times faster and with the lowest processor and disk priority.
- Reason: request of the administrator on 2026-11-04: app-log-live.py --advise took all the processor for several minutes.
- Changes:
  - Output.muted (new): while --advise reads the window, write() returns at once: nothing is translated, kept in the buffer or written. Before, each line was formatted, translated then sent to /dev/null.
  - emit(): with the output muted, the line is counted (Stats.ajouter) then left: no painting, status bar, beep or repeat watch; compose() keeps the plain text instead of the screen formatting (except with --only, which looks for its words in the shown line).
  - Resolver.lazy (new): while the window is read, no DNS, RDAP or country lookup; the fast path (this server, known people, whitelist, places) and the permanent cache stay, so the protected addresses are still recognized. New closure name_addresses(): at the end, the addresses the analysis can show (suspicious requests, 404 sweeps, account forms, recommendations of web-monitor.py; 60 at most, 20 s at most) are named, before to_ban(): a CDN relay is still recognized by its name and never proposed.
  - find_ips(): the result of the last 4096 lines is kept (_find_ips, functools.lru_cache), a copy is returned; ip_obj(): parsed addresses kept (local_address, Resolver.local, category, fast).
  - lower_priority() (new): nice 19 and ionice -c3 for --advise and the commands it starts.
  - apps/_listes.py 1.8: parsed addresses kept in the list lookups (see its section).
  - doc/fr and doc/en 07-app-log-live.md; tests: test_166_advise_nomme_les_adresses_a_la_fin and class AppLogLive166 (4 tests).
- Bugs fixed:
  - Symptom: --advise kept a processor busy for several minutes for two weeks of logs.
  - Diagnosis (cProfile on a synthetic journal of 3,000 and 20,000 lines in the test environment): 74 % of the time in the translation of each line written to /dev/null (apps/_i18n.py _remplacer); then one DNS, geoiplookup and RDAP lookup per new address (external commands); then the screen formatting of each line, find_ips() called five times per line and each address parsed eight times per line.
  - Fix: see Changes. Measured: 3,000 lines 23.4 s -> 1.6 s; 20,000 lines more than 120 s -> 7.9 s. The analysis is the same (compared line by line with the previous version on the same journal).
- Safeguards and edge cases: the live stream and the z key are unchanged (the output is muted only by --advise, the lookups are lazy only while it reads); the addresses shown by the analysis still get their names; with --only the line is still formatted to be filtered; a refused nice or a missing ionice never stops the analysis; the caches hold immutable values only (no stale answer).
- Checks performed: AppLogLive166 (copy of find_ips, muted output, lazy lookups, priority), test_166 (names looked up at the end, an address not shown never looked up), test_165 and test_163 unchanged, test_advisor, test_listes; profile and comparison of the analysis before and after.
- Action required from the user: none.

### 1.165.20261104.183145 - --advise [DAYS]: the analysis of the z key over the last weeks of logs

- Title: new option --advise [DAYS]: the analysis of the problems raised (z key) over a window of several days, without the live stream.
- Reason: request of the administrator on 2026-11-04: an option that runs what the z key does, to find things to fix over the last weeks of logs.
- Changes:
  - New option --advise [DAYS] (14 by default, at most 366): --no-follow, --no-keys and --status-every 0 implied; the window is the last DAYS days unless --since / --until are given; no line limit inside the window (ADVISE_LINES).
  - follow(): with --advise, the first read of sitemap.xml is awaited (20 s at most) so that the 404 are classified, the lines are counted with the screen sent to /dev/null, then the screen comes back and advise(batch=True) prints the analysis; --summary still prints the session summary after it; Ctrl-C brings the screen back for the summary.
  - advise(batch): with batch=True, the rotated nginx access logs written during the window (.1, .2.gz...) are read for the referers, and the history is advisor-history-advise.json; advisor_history_file(name).
  - New constants ADVISE_DAYS_DEFAULT, ADVISE_DAYS_MAX, ADVISE_LINES, ADVISE_SITEMAP_WAIT_S; lang/app-log-live.fr.po: 4 entries; doc/fr and doc/en 07-app-log-live.md.
  - Files: app-log-live.py, apps/_advisor.py, lang/app-log-live.fr.po, doc, tests.
- Bugs fixed: none.
- Safeguards and edge cases: refused with --record-test-log and outside 0 < DAYS <= 366; no daily journal is written (as with --no-follow); the history of the z key is never mixed with that of --advise (windows of different lengths); the journal of a server keeps only what its retention allows (journald SystemMaxUse / MaxRetentionSec): an older window gives fewer lines, never an error.
- Checks performed: new tests test_165_option_advise_periode_sans_afficher_les_lignes and test_165_option_advise_valeurs_refusees; test_advisor (gzip logs); help sorted alphabetically.
- Action required from the user: none. Suggested: sudo app-log-live.py --advise once a week (or as a scheduled task) and fix the problems listed first in "to fix first".

### 1.164.20261104.162540 - A language prefix is only a code of ISO 639-1: "/ev" is no longer a sitemap page

- Title: the comparison with sitemap.xml removes a first segment of two letters only when it is a language code of ISO 639-1.
- Reason: request of the administrator on 2026-11-04, after the analysis of the z key (1.163): the health was "to look at" because of one 404 on "/ev" counted as a page of sitemap.xml.
- Changes: new constant ISO_639_1; sitemap_path() removes the language prefix only when its two letters are in it (used by Sitemap.read, Sitemap.listed, the health and --log-chk-sitemap); doc/fr and doc/en 07-app-log-live.md; tests: class AppLogLive164 (2 tests).
- Bugs fixed:
  - Symptom: "404 on pages of sitemap.xml (important, in the health): 1 - URL: /ev", health "to look at".
  - Diagnosis: LANGUAGE_PREFIX_RE takes any two-letter first segment for a language prefix; "/ev" (a truncated "/event") became "/", the home page, which is in the sitemap.
  - Fix: only a code of ISO 639-1 (with or without region, "fr", "es", "fr_CA") is removed; "/ev" stays "/ev" and is counted with the 404 never in sitemap.xml (not in the health).
- Safeguards and edge cases: "/fr", "/es", "/fr_CA/...", "/en_US/..." are compared as before; a two-letter path that is a real language code the site does not offer (e.g. "/de") is still compared as the home page: the z key reports it as information.
- Checks performed: AppLogLive164 (new), AppLogLive142 and AppLogLive143 (sitemap) unchanged, test_advisor, catalogue tests.
- Action required from the user: none.

### 1.163.20261104.135312 - z key: analysis of the problems raised, with recommended solutions and history

- Title: new z key: the program analyzes the problems raised by its dashboard, reads their details in the logs and recommends solutions, compared with the previous analyses.
- Reason: request of the administrator on 2026-11-04: add an option to the menu that analyzes the problems raised, looks at the detail of the logs to understand them and recommends leads for solutions, instead of sending the logs for analysis; the analysis of the summaries must allow continuous improvement.
- Changes:
  - New key z (MENU_KEYS "advise") and its line in the keys menu (Others, alphabetical order kept).
  - New closure advise() in follow(): builds the facts, reads the details (Odoo traceback of each ERROR / CRITICAL message in the Odoo logfile, otherwise journalctl -u SERVICE -o cat around its time, at most 10 errors; codes, referers and User-Agents of the 4xx URLs in the nginx access logs of the profile), calls apps/_advisor.py, records the analysis in the history and prints the result.
  - New functions advisor_facts(stats) (counters of the summary as a plain dictionary: 5xx, 4xx without the suspicious and disabled URLs, codes per URL, 404 of the sitemap, Odoo errors with their times, conflicts, e-mails, slow requests, addresses to ban and not proposed, account forms, latency sample) and advisor_history_file() (advisor-history.json in APP_LOG_LIVE_STATE_DIR, /var/lib/app-log-live or ~/.cache/app-log-live).
  - The options of follow() carry the journal namespace ("ns") so that the journal read for the tracebacks is the one of the service.
  - The catalogue lang/_advisor.fr.po is loaded with the program (module written in English, French display); lang/app-log-live.fr.po: 5 entries.
  - Files: app-log-live.py, apps/_advisor.py (new), lang/_advisor.fr.po (new), lang/app-log-live.fr.po, doc/fr and doc/en 07-app-log-live.md, nginx-tools-tests/test_advisor.py (new), nginx-tools-tests/test_app_log_live.py, nginx-tools-tests/test_conventions.py.
- Bugs fixed: none in the program. The analysis explains a false alarm of the health: a 404 on "/ev" was counted as a page of sitemap.xml because LANGUAGE_PREFIX_RE takes any two-letter segment for a language prefix and compares the home page; the analysis says so (information, not a problem). The counting itself is not changed in this version (separate request).
- Safeguards and edge cases: read-only (the logs are only read; the only file written is the history, mode 600, written atomically); module missing: one message, no error; no writable state folder or unreadable history: the analysis is shown, the reason is given; journalctl absent or not root: "traceback not found" and the advice of the E key; at most 30 MB read at the end of each log file; a rule that fails is reported and never stops the others; addresses to ban are only proposed (key b, nginx-log-audit.sh keeps the white list and the score threshold 3; CDN relays are never proposed); log data (URLs, messages, names) is never translated.
- Checks performed: new nginx-tools-tests/test_advisor.py (details, rules, history, catalogue, facts, z key); new test test_163_touche_z_analyse_et_historique (pseudo-terminal: z key, French display, history written, journal read with -o cat); test_i18n and test_conventions: no new failure (the failures seen are the same on main before this change); the 8 failures of test_app_log_live seen in this environment are the same on main before this change.
- Action required from the user: none. Optional: run app-log-live.py with sudo so that the systemd journal (tracebacks) and /var/lib/app-log-live (history) are readable.

### 1.162.20261103.121212 - Enter shows the status bar with the time; SSH count fixed; users logged in (who)

- Title: Enter prints the status bar with the current date and time, the SSH count is fixed and the accounts listed by who are shown.
- Reason: three requests: (1) when waiting for new lines, a way to see that the program is alive and the counters, with the time of the action; (2) add the users logged in to the server (visible with who); (3) the SSH count in the status bar was always 0.
- Changes: app-log-live.py: KEYS maps Enter (CR and LF) to "enter"; key() prints status_line(now_stamp=True): date and time first, no legend "since the last detailed report", counters not reset. New functions ssh_by_user, ssh_count (ps and who combined, as in the reports) and who_users (every session of who). StatusBar.pieces and summary take a third argument and show "logged in (who) N (names)". The keys menu lists Enter. lang/app-log-live.fr.po: 2 entries. Files: app-log-live.py, lang/app-log-live.fr.po, doc/fr and doc/en 07-app-log-live.md, tests.
- Bugs fixed: symptom: "SSH 0" in the status bar while sessions were open. Diagnosis: the bar used only the lines of who that carry an origin address, so a server whose who is empty or without origin (no utmp, console, sessions without a terminal) always gave 0, while the reports also counted the sshd processes. Fix: the bar uses the same count as the reports.
- Safeguards and edge cases: Enter is read only while the live stream runs (questions and the menu take the terminal back, so their answers are not affected); who or ps absent gives 0 and an empty list, never an error; at most 5 account names are shown, then "+N".
- Checks: new test_162 (ps only, who without origin, both absent, Enter mapping); test_utilisateurs_ssh_et_nombre_de_sessions unchanged; catalogue test for this program.
- Action required: none.

### 1.161.20261103.112057 - --theme N: color themes

- Title: --theme N: color themes.
- Reason: request of the administrator on 2026-11-03: a --theme N option for all the programs (dark background, light background, etc.), making sure that every color reads on the chosen background. Delivered first for app-log-live.py, web-monitor.py and nginx-log-audit.sh; the other programs follow on request.
- Changes:
  - New option --theme N (0 to 4) and key THEME of the configuration (SCHEMA_CONFIG, common key of app-default.conf).
  - theme_sgr(): color_code(), highlight and the version numbers of --changelog go through apps/_theme.py; THEME_MODULE is loaded after the options are read and exports NGINX_TOOLS_THEME to the programs started.
  - lang/app-log-live.fr.po, doc/fr and doc/en (07-app-log-live.md, 00-overview.md, app-log-live.conf.example); tests: test_theme.py.
- Bugs fixed: none.
- Safeguards and edge cases: theme 0 changes nothing (default); without the module apps/_theme.py the colors of the terminal are kept; NO_COLOR and redirected output still remove every color; the priority is --theme, THEME of the file, THEME of app-default.conf, NGINX_TOOLS_THEME.
- Checks performed: test_theme.py (every color code of the program, for each theme), test_i18n, app-log-live tests AppLogLive156 to 160.
- Action required from the user: none. To use a theme everywhere: THEME=2 in /etc/default/app-default.conf (or ~/.app-default.conf), or --theme N on one run; python3 apps/_theme.py --demo shows the themes.

### 1.160.20261103.100730 - Startup lines in the ? key, backslash requests merged

- Title: startup information moved to the ? key; nginx and Odoo lines of a request with a backslash merge.
- Reason: request of the administrator on 2026-11-03: (1) the nginx line "register%5C" and the Odoo line "register\\" were shown apart although they are the same request; (2) the startup lines (nginx logs, Odoo service, sign-in history, modules warning, colour legends, banned addresses, screen, daily log) must be in the ? key, and the line "Startup information: press ?" removed.
- Changes:
  - New key_url() used by request_key(): decoded URL where %5C, a literal x5C escape and a doubled backslash give one backslash.
  - STARTUP_HIDE_RE (lines always kept for the ? key); the capture starts right after the title and ends just before follow(); STARTUP_KEEP_RE gets "Test recording"; the pointer line "Startup information ... press ?" and its catalogue entry are removed (the "Keys:" line names the ? key); the --modules-startup lines stay on screen.
  - doc/fr and doc/en 07-app-log-live.md; tests: class AppLogLive160 (3 tests).
- Bugs fixed:
  - Symptom: GET /x/register%5C (nginx) and GET /x/register\\ (Odoo) stayed as two lines. Diagnosis: request_key() decoded %5C into one backslash but Odoo's log shows two. Fix: key_url() collapses every spelling.
- Safeguards and edge cases: real problems (ERROR, WARNING, RECOMMENDED, filters, excluded addresses) stay on screen; without a terminal, with --no-keys or in a pipe everything is printed as before; the PostgreSQL warning of the modules is now only in the ? key.
- Checks performed: AppLogLive156 to 160; test_i18n and changelog checks for app-log-live.
- Action required from the user: none.

### 1.159.20261103.100102 - BOT code for named robots, tool codes in yellow, robot 403 in yellow text

- Title: the system column shows BOT for named robots and colours the tool codes; a 403 from a refused robot no longer uses reverse video.
- Reason: request of the administrator on 2026-11-03: (1) change the colour of the 403 errors generated by bots, which are not critical, from yellow reverse video to yellow text, but keep reverse video for sensitive files; (2) the system column still showed OTH for robots (NVIDIABOT, Amazonbot, SemrushBot...) and the colour should flag suspect ones (like curl).
- Changes:
  - New BOT_UA_RE and code BOT in os_code(), checked first (a robot such as Googlebot Mobile has a system in its text); OS_COLORS: BOT magenta, tool codes (CUR, PYT, WGT, GOL, JAV, PHP, NOD, RUB, PER) bold yellow.
  - STYLES["url_bot"] = "93": the URL of a 403 answered to a User-Agent of the bot_blocker.conf list (is_bot_403) is yellow text; the other 4xx keep url_warning (reverse video); a suspicious URL (sensitive file) is painted first and keeps its reverse video.
  - doc/fr and doc/en 07-app-log-live.md. nginx-tools-tests/test_app_log_live.py: new class AppLogLive159 (4 tests); AppLogLive156 adapted (Googlebot is now BOT).
- Bugs fixed:
  - Symptom: facebookexternalhit showed PHP in the system column. Diagnosis: the pattern \bphp\b of 1.156 matched "externalhit_uatext.php" in its User-Agent. Fix: PHP only at the start of the User-Agent or as "php/N"; and the robot check comes first.
- Safeguards and edge cases: CUBOT phones (Android) are not taken for robots; the NVIDIA robot does not give "curl" in its User-Agent, so it is BOT, not CUR; unknown programs and clients such as Ecosia/CFNetwork stay OTH.
- Checks performed: AppLogLive156 and 159 (6 tests); syntax check.
- Action required from the user: none.

### 1.158.20261103.085742 - --errors-only: only the errors and the suspicious requests (X key)

- Title: new option --errors-only (ERRORS_ONLY, X key as a toggle while the program runs) that hides the normal transactions and shows only the errors and the suspicious requests, starting with the last 100 errors.
- Reason: request of the administrator on 2026-11-03: "add an option (command line and in the menu as a toggle) to see only the errors (or suspicious requests), not the normal transactions without errors (show the last 100 errors); in the menu while the program runs it must be a toggle."
- Changes:
  - New is_error_line(): HTTP code 400 and above, suspicious request (SUSPECT_RE, even answered 200), Odoo WARNING / ERROR / CRITICAL, trace, failed login. A continuation line (Python trace) follows the line before it (error_flag).
  - keep(): the filter also requires an error when the mode is on (it combines with --suspect, --only, --not-found, --exclude-ip).
  - A buffer of the last 100 errors (ERRORS_SHOWN) is kept all the time. At the start the history is held and its last 100 errors are shown first ("──── N dernières erreurs (--errors-only) ────"; "aucune erreur dans l'historique" if none); at least 3000 lines of history are read (ERRORS_HISTORY_LINES). The history ends at the first recent line, at the end of the stream, or when the stream is idle after some lines.
  - X key (MENU_KEYS "errors"): toggles the mode; switching it on shows the last 100 errors already seen again (not counted twice in the summary). Menu line and ERRORS_ONLY in the configuration file (saved by the W key), in the list of the --config help.
  - lang/app-log-live.fr.po, doc/fr and doc/en 07-app-log-live.md and app-log-live.conf.example. nginx-tools-tests/test_app_log_live.py: new class AppLogLive158 (5 tests).
- Bugs fixed:
  - Found while testing: a first version stored its flag in the attribute L.err, which hid the method Line.err() used by --min; renamed L.error_seen.
- Safeguards and edge cases: the summary counts only the displayed lines, as with --suspect; the history is held only for lines older than the start of the program; an idle stream without any line does not print "no error" before 15 s; the key does nothing else (no restart).
- Checks performed: AppLogLive156, 157 and 158 (11 tests); test_i18n catalogue of app-log-live.
- Action required from the user: none.

### 1.157.20261103.081106 - Password reset and sign-up forms in red reverse video, counted per address

- Title: requests to /web/reset_password and /web/signup are shown in red reverse video and counted in the summary.
- Reason: request of the administrator on 2026-11-03: address 206.42.109.58 (SofyaBot) made hundreds of requests to the password reset, sign-up and login pages; "watch these Odoo URLs and show them in red reverse video".
- Changes:
  - New ACCOUNT_FORM_RE (with or without language prefix) and style STYLES["account"] = "7;31" (red reverse video); render() paints the URL with it before the login style (suspect URLs and 5xx errors keep their own style).
  - Stats: new counters account_ips and account_urls (in COUNTERS, so Ctrl-T and the periods reset them); the summary shows the line "Account forms" with the first five addresses; the addresses of the server itself are not counted.
  - lang/app-log-live.fr.po: the new messages. doc/fr and doc/en 07-app-log-live.md. nginx-tools-tests/test_app_log_live.py: new class AppLogLive157 (4 tests).
- Bugs fixed: none.
- Safeguards and edge cases: /web/login and /web/session/authenticate keep the blue login style (a normal member logs in); a longer path that only starts like the forms (e.g. /web/signup-x) is not matched; the colour is added without changing the text, so the columns stay aligned.
- Checks performed: test_app_log_live.AppLogLive157; syntax check.
- Action required from the user: none.

### 1.156.20261102.235216 - System column: the program (CUR, PYT...) replaces OTH

- Title: in the system column of the nginx lines, a User-Agent without a system now shows the program that makes the request (CUR curl, PYT Python, WGT wget, GOL Go, JAV Java, PHP, NOD Node.js, RUB Ruby, PER Perl) instead of OTH.
- Reason: request of the administrator on 2026-11-02: "for the User-Agent, you show the OS as WIN and OTH for others; replace OTH by the program used, CUR for curl or PYT for Python."
- Changes:
  - New table PROGRAM_CODES; os_code() looks at the system first (AND, IOS, WIN, LIN, MAC), then at the program, and keeps OTH for any other User-Agent (browsers of unknown systems, crawlers such as Googlebot).
  - doc/fr and doc/en 07-app-log-live.md: the codes. nginx-tools-tests/test_app_log_live.py: new class AppLogLive156 (2 tests).
- Bugs fixed: none.
- Safeguards and edge cases: the system has priority (a browser User-Agent that mentions a tool name stays WIN or LIN); no User-Agent ("-", Odoo lines) keeps three blanks; the column width does not change (3 characters); words are matched as whole words (curl, wget, java, php, node...) so a name inside another word does not match.
- Checks performed: test_app_log_live.AppLogLive156; syntax check.
- Action required from the user: none.

### 1.155.20261102.230844 - An address is proposed for banning only if nginx-log-audit.sh --investigate recommends it

- Title: the b key, the summary and the background proposal ask nginx-log-audit.sh --investigate, the program that bans, before proposing an address; only its verdict "BANNIR" is proposed, the others are listed with that verdict.
- Reason: request of the administrator on 2026-11-02: "app-log-live.py suggested banning two IPs, but the program it calls, nginx-log-audit.sh, does not; adjust and synchronise the logic." 132.196.59.85 and 45.138.12.41 came from recommended-bans.json (an old recommendation of web-monitor.py, kept 48 h, reason "récidiviste : ... bannissements temporaires répétés"), and the background proposal used the verdict of --evidence ("bannissement justifié"), while --ban requires the score of the investigation.
- Changes:
  - New function audit_verdict(ip, app_args): runs nginx-log-audit.sh --investigate IP --no-prompt (background, NGINX_TOOLS_LANG=fr, INV_RESUME_FILE) and reads its line "RÉSUMÉ|ip|verdict|reason|bans"; with an older nginx-log-audit.sh, its line "Score N/7 : bannissement recommandé". New constant AUDIT_TTL (30 minutes).
  - Stats: new shared dictionary audit (address -> instant, verdict, reason, fail2ban bans) and method audit_fresh; to_ban() leaves out an address whose fresh verdict is not "BANNIR" and names it in not_proposed ("nginx-log-audit.sh : AUCUNE ACTION - ..."), so the dashboard, the menu count and the summary follow the same verdict.
  - b key (ban()): the candidates not yet checked are checked first ("Vérification de N adresse(s) par nginx-log-audit.sh --investigate (le programme qui bannit décide)..."), one at a time (investigation_lock); then the addresses not proposed are listed with the verdict, and each proposed one shows the reason of the investigation.
  - evaluate_repeat() (background proposal of an often-banned address): the verdict of --investigate instead of --evidence; proposed when "BANNIR" and at least REPEAT_MIN fail2ban bans. Texts "verdict : bannissement justifié" -> "verdict de l'enquête : bannir"; help of --no-ban-prompt.
  - lang/app-log-live.fr.po: the new and changed messages; doc/fr and doc/en 07-app-log-live.md: the b key.
  - nginx-tools-tests/test_app_log_live.py: new class AppLogLive155 (5 tests); test_adresse_bannie_souvent_proposee_avec_delai and test_adresse_bannie_souvent_sans_reponse_ou_verdict_different_ou_option adapted to the new contract (their fake nginx-log-audit.sh answers --investigate with a summary line instead of --evidence).
- Bugs fixed:
  - Symptom: "2 adresses à bannir", then "LES PREUVES NE JUSTIFIENT PAS CE BANNISSEMENT ... Tapez exactement BANNIR". Diagnosis: three sources (suspicious requests seen here, 404 sweeps, recommended-bans.json) and the --evidence verdict were trusted without the rule of --ban. Fix: the verdict of --investigate decides.
- Safeguards and edge cases: the investigation runs only when the b key is pressed (or in the background for an often-banned address), never for each line; a verdict is kept 30 minutes; investigation impossible (program missing, timeout): the address stays proposed and --ban still checks it, as before. Older nginx-log-audit.sh without the summary line: its "Score" line is read.
- Checks performed: python3 -m py_compile; AppLogLive155 (5 tests) and the two adapted tests [OK]; test_app_log_live: 221 tests, the 7 failures already present on main; test_i18n: catalogue of app-log-live [OK].
- Action required: none (with nginx-log-audit.sh 2.79 or later next to it, the verdicts match exactly).

### 1.154.20261102.220415 - Column header: country and IP block labels with --min, and the header again after each status bar

- Title: the header line shows "PA BLOC-IP" (English "CC IP-BLOCK") over the country code and the name, also with --min; it is shown again right after each status bar.
- Reason: request of the administrator on 2026-11-02: the header "HEURE PROG NIV ... HTTP STA SIZE..." lacked the country and the IP block over "CA JoséR+MartialB+Rencontres-LinuxQ+Administrat..." of an http line; and the header should come after the status line.
- Changes:
  - column_header(): one label TR("CC IP-BLOCK") placed on the country code of the measured line (two capital letters followed by the name), or on the address when there is no country code; it replaces the two labels TR("CC") and TR("IP BLOCK (ISP)").
  - New inner function header_after_bar(): show_header() measured on the last request line written (state["header_plain"], kept by paint()), or on a sample before the first one. Called after the periodic status bar (emit) and after the status bar shown once after the history (startup_status_bar).
  - lang/app-log-live.fr.po: "CC IP-BLOCK" -> "PA BLOC-IP" (the entries "CC" and "IP BLOCK (ISP)" removed).
  - doc/fr and doc/en 07-app-log-live.md: the header after the status bar and the label.
  - nginx-tools-tests/test_app_log_live.py: new class AppLogLive154 (4 tests).
- Bugs fixed:
  - Symptom: no country / IP block label over the name of an http line with --min. Diagnosis: column_header() skipped two words after the level, the logger ("base werkzeug") of a normal line; with --min there is no logger, so the label landed on "H1.1" and was left out (or, with a country and a name, after the name). Fix: the label is placed on the country code found in the line.
  - Symptom: the label "CC" stayed "CC" in French. Diagnosis: the shared translator (apps/_i18n.py) leaves texts shorter than 3 characters untranslated. Fix: one longer label "CC IP-BLOCK".
- Safeguards and edge cases: logger names are in lower case, so they are never taken for a country code; a label that would overlap the request columns is still left out (narrow terminal); the header is decoration, an error while measuring it never stops the stream; it goes to the error output as before, not to the daily journal. --status-every 0: no status bar, so no extra header.
- Checks performed: python3 -m py_compile; AppLogLive154 (4 tests), AppLogLive153 and AppLogLive143 [OK]; header previewed with and without --min, with and without a country and a name.
- Action required: none.

### 1.153.20261102.201101 - --log-merge: an nginx 304 or 499 merges with the Odoo line of the same request

- Title: the nginx line and the Odoo line of one request are merged even when their status codes differ in the two ways nginx produces: 304 for a 200 of Odoo, 499 for any status of Odoo.
- Reason: request of the administrator on 2026-11-02. The merge worked for 99% of the requests, but some pairs were shown as two lines: 12:59:45 GET /en_CA/blog/presentations-3/tag/montreal-12 (nginx 499, Odoo 200), 13:26:47 GET /base/static/img/country_flags/ca.png (nginx 304, Odoo 200), 19:03:47 GET /base/static/img/country_flags/ca.png?height=25 (nginx 304, Odoo 200).
- Changes:
  - Version 1.152 -> 1.153.
  - New function merge_codes_compatible(nginx_code, odoo_code): same code, nginx 499 (any Odoo code), or nginx 304 with Odoo 200.
  - New function merge_partner(held, key, instant, partner_is_nginx): finds the held partner of a request line; same URL and within MERGE_WINDOW, an identical status code is preferred, otherwise the first compatible one.
  - merge_step(): both directions (nginx first, Odoo first) use merge_partner() instead of comparing the whole key (URL, status).
  - Documentation: doc/en/07-app-log-live.md, doc/fr/07-app-log-live.md (--log-merge): the 304 and 499 rule; the window and the wait shown as 5 s and 8 s (values of 1.145, the text still said 2 s and 3 s).
  - nginx-tools-tests/test_app_log_live.py: new class AppLogLive153 (5 tests).
- Bugs fixed:
  - Symptom: with --log-merge, some requests were shown twice, once as an nginx line (304 or 499, no SQL times) and once as an Odoo line (200).
  - Diagnosis: request_key() is (method and URL, status code) and merge_step() required the whole key to be equal. nginx answers 304 itself when Odoo's 200 carries an ETag or Last-Modified matching the browser's If-None-Match / If-Modified-Since, and writes 499 when the client closes the connection before Odoo answers; Odoo logs 200 in both cases.
  - Fix: the URL must still be equal, the status codes only compatible (merge_codes_compatible).
- Safeguards and edge cases: an identical status code always wins over a compatible one, so two requests of the same URL at the same second (one 200, one 304) are not crossed. The merged line keeps the status of nginx (304 or 499, what the browser got) and takes the SQL queries and times of Odoo. A different URL never merges (19:03:47: es.png of Odoo does not take the nginx line of ca.png). Other differences (nginx 200 / Odoo 404, nginx 304 / Odoo 500, Odoo 304 / nginx 200) never merge. The window (5 s) and the wait (8 s) are unchanged.
- Checks performed: python3 -m py_compile; AppLogLive153 (5 tests) and AppLogLive143 (merge of encoded URLs and websockets) [OK]; modules test_app_log_live and test_i18n: 244 tests, the failures are those already present on origin/main before this change (test_app_log_live: menu, Ctrl-C, addresses to ban, HTML journal 1.120, columns never squeezed, checked on main; test_i18n: nginx-log-audit, nginx-hardening, apps/_listes.sh).
- Action required: none.

### 1.152.20261102.185714 - --hide-addons also hides the lines of odoo.models.unlink and odoo.modules.registry

- Title: with --hide-addons (key q), the INFO lines "User #1 deleted ... records with IDs: [...]" (logger odoo.models.unlink) and "Invalidating caches after database signaling: [...]" (logger odoo.modules.registry) are hidden.
- Reason: request of the administrator on 2026-11-02. These lines filled the stream (for example 18:44:43 to 18:44:44: ir.cron.progress, bus.presence, mail.compose.message, mail.activity.schedule, ir.attachment, rlq.survey.report.wizard) although --hide-addons was given.
- Changes:
  - Version 1.151 -> 1.152.
  - New constant ADDONS_HIDDEN_LOGGERS = ("odoo.models.unlink", "odoo.modules.registry").
  - Line.discard_addons(): a line is also discarded when its logger is in ADDONS_HIDDEN_LOGGERS (exact name), with the same rules as for odoo.addons.*: level INFO or DEBUG only, never an error, never a line kept by ADDONS_KEEP_RE (e-mails sent, generated files).
  - Help of --hide-addons (command line and key q menu) names the two loggers; lang/app-log-live.fr.po: the two entries updated (msgid and msgstr).
  - Documentation: doc/en/07-app-log-live.md, doc/fr/07-app-log-live.md, doc/en/app-log-live.conf.example, doc/fr/app-log-live.conf.example.
  - nginx-tools-tests/test_app_log_live.py: new test test_hide_addons_cache_unlink_et_registry_sauf_erreurs.
- Bugs fixed:
  - Symptom: with --hide-addons, the lines of odoo.models.unlink and odoo.modules.registry were still shown.
  - Diagnosis: discard_addons() only tested the prefix "odoo.addons."; these two loggers belong to the Odoo core (odoo.models, odoo.modules), not to a module.
  - Fix: the two logger names are added to the test (ADDONS_HIDDEN_LOGGERS).
- Safeguards and edge cases: WARNING, ERROR, CRITICAL lines and traces of these loggers are never hidden. Exact names only: odoo.modules.loading ("Modules loaded.") and the other loggers of the core are still shown. Without --hide-addons nothing changes. The lines hidden are counted with the others (key q shows the count). Same filter for the lines refreshed on screen and for the history.
- Checks performed: python3 -m py_compile; new test and existing test test_hide_addons_cache_le_bruit_des_modules_sauf_erreurs_courriels_et_pdf [OK]; test_i18n: the app-log-live catalogue [OK]. Failures also present on origin/main before this change, not caused by it: 6 tests of test_app_log_live.py (menu, Ctrl-C, addresses to ban, HTML journal 1.120) and 3 of test_i18n (nginx-log-audit, nginx-hardening, apps/_listes.sh).
- Action required: none.

### 1.151.20261102.151239 - Bans read from the fail2ban journal: the report shows when an attacker was banned

- Title: app-log-live.py reads the fail2ban journal, so an address banned after an attack is shown with its ban time and its jails.
- Reason: request of the administrator on 2026-11-02. The address 34.173.12.79 (reverse name 79.12.173.34.bc.googleusercontent.com) sent about 43 probes for sensitive files (.env, credential files, /proc/self/environ) between 07:41:22 and 07:41:23. Three fail2ban jails banned it at 07:41:23 (nginx-badrequests, nginx-blocked-probes, nginx-sensitive-files). The dashboard showed "banned: 0" and "Addresses to ban: none", with no trace of that ban. The administrator asked for the program to read the fail2ban journal too, so that an attack followed by a ban is visible.
- Changes:
  - Version 1.150 -> 1.151.
  - New Bans.read_fail2ban_journal(): reads the lines "NOTICE [jail] Ban IP" of the fail2ban journal (last 20 MB), per address, with their local time and jail. Read at startup and every 60 seconds with the other bans, in refresh().
  - New Bans.ban_before() (last ban of an address at or before a line, within BAN_LABEL_WINDOW = 86400 seconds) and Bans.first_ban_of() (first ban and jails of an address). Constants: FAIL2BAN_LOG, FAIL2BAN_TAIL, FAIL2BAN_BAN_RE, BAN_LABEL_WINDOW.
  - compose(): a line of an address banned by fail2ban after that request is labelled "[banned: fail2ban HH:MM:SS]" (nginx lines: [BANNIE]). Such an address counts as banned in "Banned addresses seen".
  - Stats.fail2ban_note(): the "by address" line of the suspicious requests shows " [fail2ban: banned at DATE TIME (jails)]".
  - Environment variable APP_LOG_LIVE_FAIL2BAN_LOG (default /var/log/fail2ban.log): the same variable already names the journal recorded with --record. No new option, no new configuration key.
  - Files touched: app-log-live.py, lang/app-log-live.fr.po (new message "fail2ban: banned at"), nginx-tools-tests/test_app_log_live_fail2ban.py (new), nginx-tools-tests/test_app_log_live_ban.py (version test), CHANGELOG.md.
- Bugs fixed:
  - Symptom: an address banned a few seconds after a burst of attack requests was shown as "banned: 0" and "Addresses to ban: none"; the ban did not appear anywhere in the report.
  - Diagnosis: class Bans only read the bans active at the moment of each read (fail2ban-client banned, every 60 seconds). The attack lines, read before the ban, never received a label, and no source gave the time of the ban. Separately, test_app_log_live_ban.py asserted the hard-coded version 1.149, already outdated when 1.150 was released.
  - Fix: the fail2ban journal is read (ban lines only); the ban time and jails are shown on the lines that follow it and in the report. The version test now checks the format of the version, not its value.
- Safeguards and edge cases:
  - Read only: the new code calls no fail2ban-client set, banip or unbanip (a test checks it). Nothing is banned or unbanned by this change.
  - Precision: fail2ban writes milliseconds, the time is kept to the second. A request in the same second as the ban can be labelled.
  - Unreadable journal (no root, no file, no fail2ban): None, no label, no error.
  - Labels only for 86400 seconds after a ban. Only the last 20 MB of the journal are read; older rotations are not read.
  - Whitelist and places are never labelled, as before.
  - Several jails banning the same address in the same second: the jail with the largest name is shown (deterministic).
- Checks performed: py_compile; --version prints 1.151.20261102.151239; --help exits 0; sample journal (three jails, one IPv6 address, one Unban line ignored) parsed as expected; test_app_log_live_ban and test_app_log_live_fail2ban: 19 tests OK. Full run of nginx-tools-tests/run-all.sh: see the pull request.
- Action required from the user: none for this change. Separately, the investigation of 34.173.12.79 reported that SMTP is not configured (SMTP_HOST and NOTIFY_EMAIL_TO empty) and that /opt/odoo/erplibre/run.sh still passes --limit-memory-hard=0. These are outside this change and must be fixed on the server (nginx-hardening.sh --check). The address is already banned by three jails until 2026-11-03 07:41:23. The address 79.12.173.34, which was banned by mistake through the manual command, must be unbanned: sudo fail2ban-client set nginx-blocked-probes unbanip 79.12.173.34.

### 1.150.20261102.080324 - Nginx and Odoo lines in time order: a late line is placed, not shown out of order

- Title: the nginx lines merged with the Odoo lines (--log-nginx) are no longer displayed out of order.
- Reason: the merge of nginx and Odoo lines was out of order in the live display (lines of 01:45:44 before lines of 01:45:43). The owner asked for the merge code to be fixed in this program; the merge itself lives in apps/_logs_merge.py, changed in version 1.2 of that program.
- Changes:
  - Version 1.149 -> 1.150. The comment of the NGINX LOGS section describes the merge window (APP_LOG_MERGE_WAIT, 1.5 seconds by default). The merge is not reconfigured: no new option, no new configuration key.
  - Files touched: app-log-live.py, apps/_logs_merge.py, nginx-tools-tests/test_logs_merge.py, CHANGELOG.md.
- Bugs fixed:
  - Symptom: a nginx line appeared after an Odoo line that had a later log time (for example 01:45:44 before 01:45:43), in the merged stream.
  - Diagnosis: apps/_logs_merge.py declared a silent stream "stalled" after 2 seconds and released the lines of the other streams at once. A nginx line delivered after that moment came out after the Odoo lines that had a later time. The 1.115 entry accepted this as a trade-off.
  - Fix: see apps/_logs_merge.py 1.2.
- Safeguards and edge cases:
  - The reader threads never wait: the display loop only takes the lines that are due.
  - A silent stream never holds back the others (the wait is per line, not per stream).
  - A line that arrives later than the window is still displayed, in its arrival place, and counted (Merger.late); it is not dropped.
- Checks performed: py_compile; --version gives 1.150.20261102.080324; test_logs_merge: 13 tests OK (4 new ones on the window: late line placed in time order, silent stream, start with the history of each file, end of every stream).
- Action required from the user: none. The merge is updated on the next run of app-log-live.py; the nginx access log still has one-second precision (see the next version of nginx-odoo-config for $msec).

### 1.149.20261101.231500 - Answers typed in line mode (echo and erase)

- Title: the answer to the questions of app-log-live.py (b key, ban justified proposal, keys) goes through saisie() of apps/_i18n.py: echo and erase (ECHOE) are set before reading.
- Reason: the Backspace key showed "^H" instead of erasing, on every prompt of the administration programs (see nginx-hardening.sh 2.74 and apps/_i18n.py 1.22, PR 154).
- Changes: ask() calls I18N_MODULE.saisie(prompt_text) when the module is loaded, input() otherwise. Version 1.148 -> 1.149. Test: test_app_log_live_ban.py checks the call.
- Bugs fixed: symptom: "^H" displayed when erasing. Diagnosis: ECHOE off on the terminal with ICANON on. Fix: the terminal is put back in line mode before each answer (tty.setcbreak is restored by keys.interactive() first).
- Safeguards and edge cases: without the module (apps/_i18n.py missing), input() as before; without a terminal, saisie() calls input().
- Checks performed: py_compile; static test test_app_log_live_ban.py.
- Action required from the user: none.


### 1.148.20261101.225430 - One address at a time: no bulk ban, no --yes

- Title: app-log-live.py no longer bans several addresses at once. Each ban goes through nginx-log-audit.sh --ban, in the foreground, on a terminal.
- Reason: request of the administrator: no bulk ban anywhere; each ban must be justified again by the detailed investigation (nginx-log-audit.sh --investigate), with the --reason exception and the word BANNIR typed by hand. app-log-live.py still called "--ban IP --yes" in two places, which bypassed that gate.
- Changes:
  - ban() (key b): the question is now "[c] yes  [N] none"; the "[y] all" choice is removed. Each address is banned by "nginx-log-audit.sh --ban IP --reason ..." in the foreground (keys.interactive() and foreground_child()), with its own investigation and its own BANNIR gate. No "--yes" anywhere in the program.
  - ban() without a terminal (no keys, stdin not a terminal): nothing is banned; the program says so.
  - propose_ban() (often banned address, verdict "ban justified"): the same foreground call for that one address, after the yes answer. The gate of nginx-log-audit.sh decides; the program no longer forces the ban.
  - Catalogue lang/app-log-live.fr.po: the prompt, the summary line and the no-terminal message are translated.
  - Version 1.147 -> 1.148.
  - Test: nginx-tools-tests/test_app_log_live_ban.py (new): no "--yes" in the program, no "[y] all" choice, terminal check before the ban, two foreground calls to "nginx-log-audit.sh --ban", version.
- Bugs fixed: symptom: pressing b and answering "y" banned every candidate in a row, with --yes, without the investigation gate. Diagnosis: the bulk branch called "--ban IP --yes" through run_captured. Fix: the branch is removed (see Changes).
- Safeguards and edge cases: a candidate banned by hand stays in stats.all_banned; an interrupted ban (Ctrl-C) is handled by nginx-log-audit.sh, which asks its own confirmation; no nginx-log-audit.sh file: nothing is attempted; no terminal: refused.
- Checks performed: py_compile of app-log-live.py; static tests of test_app_log_live_ban.py (to be run by the testeur agent with the module list); catalogue entries used by test_i18n.py.
- Action required from the user: none. To ban an address now, use "b" on a terminal and answer "c", then answer each investigation.

### 1.147.20261101.172052 - Times within 5 columns, 404 kinds in the 4xx detail, new header labels, ? for the startup information, W to save, menu entries

- Title: a BOT label and a total above 1000 s no longer shift the line; the 404s appear inside the 4xx detail of the status bar; the header uses HOUR, LVL, CC and IP BLOCK (ISP); h opens the keys menu and ? shows the startup information; W saves the settings; --menu gets two sorted modules tables and --not-found.
- Reason: the user's review of 1.146: (1) the [BOT] label moved the rest of the line by one character, and so did a time above 1000 s (2186.2 is 6 characters); (2) the status bar should read "4xx 9 (404s=0, 404b=0, 404o=9)" instead of a separate "(404: 9)" and a separate 404 group; (3) the header must show the time, the level, the country, and the owner of the address block (ISP); (4) the startup information (lists, modules, cache, colours, keys) must not be printed at startup but on demand with ?; h opens the menu; (5) the save key is W, not C; (6) the --menu entries: modules sorted by name and by date, and --not-found.
- Changes:
  - hundredths(): a time of 1000 s or more has no decimal (2186), a time from 100 s to 1000 s has one decimal, below 100 s two decimals. The value always fits the 5 columns.
  - aligned_request and aligned_nginx_request: "[BOT]" is 5 characters wide (rjust(5), was 6). The merged and Odoo times are never wider than their column.
  - StatusBar.codes_pieces(): for the 4xx group, the 404 answers are split when every one of them is classified (StatusBar.kinds_404(): sitemap, refused on purpose, never in the sitemap): "4xx 45 (403: 3 · 404s=3 · 404b=2 · 404o=40)". Otherwise (sitemap not read yet), the former "404: n" form. The separate 404 group of 1.146 is removed.
  - column_header(): labels HOUR (time), PROG, LVL (level), CC (country code) over the name column, then IP BLOCK (ISP) 3 characters further. The name column is found after the logger ("base werkzeug "), as the address and name are displayed there. Checked on a rendered line: the labels sit over the fields of the data (time, level, name).
  - Startup information: while the startup runs, the lines that are not important are kept (STARTUP_LINES, STARTUP_INFO) and shown by the ? key ("Startup information"). The important lines stay on screen: warnings, errors, filters, excluded addresses, group of accounts, reading progress, the configuration and options lines. A hint says so. A pipe or a file, and --no-keys, print everything as before (no key to ask for it).
  - Keys: h opens the menu (help), ? shows the startup information (legend key). The menu title and the hint line name both keys. The --no-keys help text changed.
  - Save: the key is W in the menu (was C); the menu line shows W.
  - --menu: "Odoo modules table (sorted by date)" (the former entry: --modules --modules-sort date), "Odoo modules table (sorted by name)" (--modules --modules-sort name), "404 answers only (--not-found)".
  - Files: app-log-live.py, lang/app-log-live.fr.po (new strings, the changed --no-keys help and keys menu strings), nginx-tools-tests/test_app_log_live.py (AppLogLive146 test for the 404 detail; updated expectations: keys h and not ?, websocket 1731, hundredths 2186).
- Bugs fixed:
  - symptom: a line with [BOT] (or a time above 1000 s) was shifted by one character. Diagnosis: "[BOT]" was rjust(6) after the time columns became 5 wide, and "2186.2" is 6 characters. Fix: width 5 for [BOT] and an integer above 1000 s.
- Safeguards and edge cases: a time of exactly 100 s to 999.9 s keeps one decimal (5 characters). A websocket duration (merged or not) above 1000 s is an integer too (the merged column is 5 wide): 1730.555 is shown 1731. The 404 split needs every 404 to be classified: when the sitemap is not read yet, the plain "404: n" stays. The startup information is only deferred on a terminal without --no-keys: a test or a pipe still prints it. The header is aligned on the name column of the Odoo request lines; the lines without a request keep their own alignment.
- Checks performed: py_compile; --help runs; testeur on test_app_log_live and test_i18n: 238 tests, 236 pass, 2 failures already present before 1.141 (test_colonnes_jamais_tassees_pays_noms_anonymises_et_souligne_tous_les_n, test_120_journal_html_un_fichier_par_jour); AppLogLive146 covers hundredths and the 404 split; the header was rendered in both modes (IP and no IP) and checked against the data columns.
- Action required:
  1. Restart app-log-live.py. Press ? to see the startup information, h for the keys menu, W to save the settings.
  2. Check the header in your terminal: the labels should sit over the time, level, country and owner (ISP) columns. Tell me if one is off by a few characters.
  3. Still open from 1.146: the 404 on "/" (send me one nginx line of it: IP, Host, User-Agent), and whether the header should keep an IP label when the addresses are shown (--keep-ip).

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

### 1.20.20261109.153000 - Without root when sudo -n -u postgres is allowed

- Title: odoo-mail-retry.py runs as an ordinary user allowed by sudoers to reach PostgreSQL.
- Reason: request of the administrator on 2026-11-09 ([2]).
- Changes: new function postgres_without_root() (sudo -n -u postgres -- true); the refusal only when it fails; message "Without root: PostgreSQL reached with sudo -n -u postgres ..."; lang/odoo-mail-retry.fr.po.
- Bugs fixed: none.
- Safeguards and edge cases: sudo -n never asks for a password; without that permission the former refusal stays.
- Checks performed: manual run as an ordinary user [OK].
- Action required: none.

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

### 2.88.20261109.153000 - Without root: --dry-run instead of a refusal

- Title: a plain run of web-monitor.py by an ordinary user becomes --dry-run.
- Reason: request of the administrator on 2026-11-09 ([2]: every program works without root).
- Changes: main(): without root and without --dry-run, args.dry_run is set and the message "Without root: --dry-run mode ..." is shown; lang/web-monitor.fr.po.
- Bugs fixed: symptom: refusal of a plain run without root; fix: read-only run.
- Safeguards and edge cases: nothing is changed: no run recorded, no ban, no timer, no correction.
- Checks performed: manual run as an ordinary user [OK]; catalogue test [OK].
- Action required: none.

### 2.87.20261103.112153 - --theme N: color themes

- Title: --theme N: color themes.
- Reason: request of the administrator on 2026-11-03: a --theme N option for all the programs (dark background, light background, etc.), making sure that every color reads on the chosen background. Delivered first for app-log-live.py, web-monitor.py and nginx-log-audit.sh; the other programs follow on request.
- Changes:
  - New option --theme N (0 to 4) and key THEME of the configuration.
  - theme_sgr(): color_code(), the [OK] [ATTN] [FAIL] tags, the magenta of the alerts (BAD) and the version numbers of --changelog go through apps/_theme.py.
  - lang/web-monitor.fr.po, doc/fr and doc/en (04-web-monitor.md, web-monitor.conf.example).
- Bugs fixed: none.
- Safeguards and edge cases: theme 0 changes nothing; a missing apps/_theme.py is not an error; colors stay limited to a terminal (colors_on).
- Checks performed: test_theme.py (every color code of the program, for each theme), test_i18n.
- Action required from the user: none. To use a theme everywhere: THEME=2 in /etc/default/app-default.conf (or ~/.app-default.conf), or --theme N on one run; python3 apps/_theme.py --demo shows the themes.

### 2.86.20261102.224544 - VPN, Tor, relay and hosting owners read from the shared module apps/_vpn.py

- Title: the list of owners of VPN, Tor, relay and hosting blocks (VPN_OWNERS) moved to apps/_vpn.py, shared with nginx-log-audit.sh --investigate.
- Reason: request of the administrator on 2026-11-02: show the same type of address in the investigations of nginx-log-audit.sh.
- Changes: VPN_OWNERS, VPN_OWNERS_RE and VPN_PRIORITY come from apps/_vpn.py (loaded with _load_module); vpn_kind() calls _vpn.kind_of(). The list itself is unchanged. The short name of a hosting provider without a known name is the first word of the network name when the organisation says nothing ("Admin").
- Bugs fixed: none.
- Safeguards and edge cases: module missing or broken: no VPN guess (column "-"), never an error.
- Checks performed: test_web_monitor (85 tests) [OK].
- Action required: none.

### 2.85.20261101.231500 - Retour arrière : écho et effacement rétablis avant chaque réponse

- Title: every question of web-monitor.py is answered in line mode (echo and erase).
- Reason: Request of the administrator: in nginx-hardening.sh, at the prompt "Faire le setup du courriel (relais SMTP) maintenant ? [o/N] :", the Backspace key shows "d^H^H^H^H" and erases nothing. The same problem can hit every program that asks a question, so every interactive prompt of the Bash and Python programs must be checked and fixed.
- Changes: the input() wrapper of the program now calls _saisie_ligne(), which uses saisie() of apps/_i18n.py (loaded once; input() if the module is missing). Its 12 questions go through it.
- Bugs fixed: same symptom as nginx-hardening.sh 2.74 (the erase key shows ^H). Diagnosis and fix as in apps/_i18n.py 1.22.
- Safeguards and edge cases: Without a terminal (pipe, cron, stdin not a tty): nothing is changed, the programs behave as before. Stdin and /dev/tty redirections are guarded with || true (set -e). Password prompts (read -s) are not changed. The helper is defined in apps/_i18n.sh; a program without that file gets a no-op fallback. Its bulk-ban refusals (2.83) are unchanged.
- Checks performed: py_compile; nginx-tools-tests/test_saisie_terminal.py (new, static): every interactive read -p / read -e of the Bash programs has tty_ligne on its line; tty_ligne is defined and sets icanon echo echoe; saisie() is defined and used by the i18n context; apps/_menu.py has its own line reader; versions.
- Action required from the user: none. Note: PR 151 (2.84) is based on 2.83; the version line of the newer PR is kept when merging.
### 2.84.20261101.222800 - Repeat-offender alert: to watch, no ban command

- Title: the alert of the repeat offenders says "à surveiller" and no longer shows the --ban commands.
- Reason: the alert "récidivistes à bannir de façon permanente" was shown even when the investigation did not recommend the ban, and its lines included "Pour bannir" commands (see the report of 2026-11-01 22:18).
- Changes:
  - web-monitor.py: reads the new header of nginx-log-audit.sh ("Récidivistes fail2ban à surveiller"); the alert keeps the address lines and the "Enquête :" lines only.
  - The alert title becomes "nginx-log-audit.sh: repeat offenders to watch" (French entry in lang/web-monitor.fr.po).
  - The recommendation itself is unchanged since 2.83: a repeat offender is recommended only if its investigation says so.
  - Version 2.84 (minor, +0.1).
- Bugs fixed: symptom: the alert suggested banning repeat offenders without investigation. Fix: see above.
- Safeguards and edge cases: no ban is started by the alert; the decision remains with the investigation and with --ban-recommended (one by one, on a terminal).
- Checks: test_web_monitor (see the pull request for the results).
- Action required: none.

### 2.83.20261101.220544 - No bulk ban; repeat offenders recommended only after their own investigation

- Title: web-monitor.py never bans several addresses at once. A repeat offender is recommended only if its investigation (nginx-log-audit.sh --investigate) recommends the ban.
- Reason: on 2026-11-01 the pass recommended 132.196.59.85 and 45.138.12.41 as "récidivistes", with the question "Bannir maintenant ? [o] toutes". The recidivism alone was the reason, and the group answer banned them at once, without the investigation of each address. The investigation of 132.196.59.85 gave 0/7.
- Changes:
  - web-monitor.py, analyze_nginx_logs: a repeat offender from the nginx-log-audit.sh report is added to the recommendations only if investigate_ip returns a recommendation (score 3/7 or more). Otherwise it stays in the alerts as information.
  - ban(items): one address at a time, each with nginx-log-audit.sh --ban (investigation, evidence, confirmation). The --yes option is no longer used for bans from this program.
  - ask_ban(items): the group answer "[o] all" is removed. The only choices are [c] one by one and [N] none.
  - --ban-recommended: refused with --yes (ERROR, exit 2) and without a terminal. On a terminal: one by one.
  - --apply --yes: other fixes still run; the recommended addresses are listed but not banned.
  - Help text (--help, header comment) updated: --yes is no longer listed for --ban-recommended.
  - lang/web-monitor.fr.po: French entries for the new messages.
  - nginx-tools-tests/test_web_monitor.py: test of the recidivist (recommended only if the investigation says so); test of --ban-recommended with --yes (refused); test of the one-by-one answer with no --yes in the command; --apply --yes test adapted.
  - Version 2.83 (minor, +0.1).
- Bugs fixed: symptom: the group answer banned all recommended addresses without investigation. Diagnosis: the recidivism rule read the report and did not call the investigation. Fix: see above.
- Safeguards and edge cases:
  - --ban-odoo-user still calls nginx-log-audit.sh --ban IP --yes for one address after its own investigation; the gate of nginx-log-audit.sh (2.70) still requires the score 3/7.
  - The browser 403 path already called investigate_ip and is unchanged.
  - Without a terminal, no address is banned by this program.
- Checks: test_web_monitor (85 tests OK); py_compile OK.
- Action required: none. After the update, the next pass no longer offers a group ban. 132.196.59.85 and 45.138.12.41 are not banned by this change; answer N unless their investigation gives 3/7 or more.

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

### 1.27.20261109.203000 - Who the update waits for: address, country, Odoo user

- Title: when the site is busy, the wait and --check-activity list who is active: address, country, Odoo user, requests and writes.
- Reason: request of the administrator on 2026-11-09: "indique que l'on attend après quels utilisateurs et IP (avec son pays)".
- Changes: new function who_waits() ("I|" lines: addresses of the nginx logs of the last VISITOR_WINDOW minutes, robots and this server left out; country from the cache of the suite apps/_cache_ip.py, otherwise geoiplookup, otherwise the country noted by Odoo; Odoo user from res_device_log (login and name, last activity in max(VISITOR_WINDOW, CONNECTED_WINDOW) minutes, revoked sessions left out); then the Odoo users active from another address; 8 lines at most); new site_reasons_who(); wait_for_quiet_site() and rapport_activite() show them without a bullet, outside the summary of the cancellation; nginx_writes() shows the address of each write; rapport_activite() no longer shows the "W|" / "R|" tags; lang/odoo-update-module.en.po; doc 09-odoo-update-module.md (fr, en).
- Bugs fixed: symptom: --check-activity showed "· W|..." and "· R|..."; diagnosis: the tag of site_reasons was not removed there; fix: removed.
- Safeguards and edge cases: reads only; database unreadable: addresses and countries without users; no country found: "pays inconnu"; --anonymize applies to these lines like to the rest of the output; geoiplookup is not called in the tests.
- Checks performed: test_odoo_update_module test_227_qui_on_attend, test_226, test_199 [OK]; test_i18n: no new failure; ShellCheck 0.11.0 [OK].
- Action required: none.

### 1.26.20261109.191500 - Bus polls are not writes; chat, presence and visitor tracking are light writes

- Title: the update is no longer cancelled by the polls of the Odoo bus nor by the live chat.
- Reason: report of the administrator on 2026-11-09: update cancelled after 2 min, the only "write" being "POST /bus/has_missed_notifications" (non critical: chat, the service comes back quickly).
- Changes:
  - nginx_writes(): READ_POST also has bus/*, longpolling/*, websocket, mail/thread/messages, mail/(inbox|starred|history)/messages, discuss/channel/(messages|info|members) (reads); new LIGHT_POST: im_livechat/*, discuss/*, mail/message/(post|reaction|update_content), mail/link_preview, mail/thread/(un)subscribe, mail/(read|set|unstar)*, website/track*, website/update_visitor_timezone, call_kw of res.users.settings, discuss.channel, mail.message, mail.notification, bus.presence; output "WRITES LIGHT" then "W ..." and "L ..." lines.
  - site_reasons(): light writes reported as "R|" (like visitors: the update goes ahead at the end of the wait), real writes still "W|" (cancel).
  - New configuration key LIGHT_WRITES (regular expression of more light addresses, without the first "/"); doc/fr, doc/en odoo-update-module.conf.example and 09-odoo-update-module.md; lang/odoo-update-module.en.po.
  - nginx-tools-tests/test_odoo_update_module.py: test_226_bus_et_discussion_ne_bloquent_pas, test_226_vraie_ecriture_bloque_toujours_et_light_writes.
- Bugs fixed: symptom: "site toujours en écriture après 2 min ... la plus récente : POST /bus/has_missed_notifications", update cancelled; diagnosis: the bus poll of the browser (sent with POST, reads only) was counted as a write; fix: read-only list completed, chat and presence classified as light writes.
- Safeguards and edge cases: a real write (survey, form, sale...) still cancels the update, --force-busy included; an invalid LIGHT_WRITES expression is ignored (the writes stay real writes), never a reason to update blind; an unreadable log still counts as a write.
- Checks performed: test_odoo_update_module (test_199, test_226) [OK]; test_i18n: no new failure; ShellCheck 0.11.0 [OK].
- Action required: none (LIGHT_WRITES only if another module sends harmless writes).

### 1.25.20261109.190000 - Erase key (^H) in the questions, ETAIT_ACTIF unbound after Ctrl+C

- Title: the questions of the site settings accept the erase key of every terminal; Ctrl+C confirmed during these questions no longer ends with an error.
- Reason: report of the administrator on 2026-11-09: "Attente maximale ... [60] 3^H^H", then "line 1085: ETAIT_ACTIF: unbound variable" after Ctrl+C.
- Changes: question_reponse(): tty_ligne then "read -e -r -t SECONDS -p QUESTION" (readline, prompt and echo on standard error), answer cleaned by appliquer_effacements(); interrupted_cleanup() and the restart after a failure use ${ETAIT_ACTIF:-0}; the other question (rollback) by read -e; fallback appliquer_effacements when apps/_i18n.sh is absent.
- Bugs fixed:
  - symptom: in a question, the erase key showed "3^H^H" and the answer kept the ^H characters; diagnosis: the kernel line mode (stty icanon echoe, put back by tty_ligne) knows ONE erase key only (stty erase, usually ^?), while some terminals (PuTTY, some ssh clients) send ^H; ECHOE does not help when the key is not the erase key; fix: the answers are edited by readline (read -e) or by our own line editor, where ^H AND ^? erase; question_reponse() used a plain "read -r -t", not seen by the static test (it looked for -p or -e only).
  - symptom: "ETAIT_ACTIF: unbound variable" when Ctrl+C is confirmed during the site questions; diagnosis: the variable is set after these questions, set -u; fix: default 0.
- Safeguards and edge cases: the 10 s timeout is kept (no answer = value in brackets); without a terminal the configured values are used as before.
- Checks performed: test_saisie_terminal (pseudo-terminal with stty erase ^?: ^H, ^?, Enter alone) [OK]; ShellCheck 0.11.0 [OK].
- Action required: none.

### 1.24.20261101.231500 - Retour arrière : écho et effacement rétablis avant chaque réponse

- Title: the backup-restore question restores echo and erase first.
- Reason: Request of the administrator: in nginx-hardening.sh, at the prompt "Faire le setup du courriel (relais SMTP) maintenant ? [o/N] :", the Backspace key shows "d^H^H^H^H" and erases nothing. The same problem can hit every program that asks a question, so every interactive prompt of the Bash and Python programs must be checked and fixed.
- Changes: tty_ligne placed before the read of "Retour arrière vers les versions d'avant". Fallback definition after apps/_i18n.sh is loaded.
- Bugs fixed: same symptom as nginx-hardening.sh 2.74. Diagnosis and fix as in apps/_i18n.py 1.22.
- Safeguards and edge cases: Without a terminal (pipe, cron, stdin not a tty): nothing is changed, the programs behave as before. Stdin and /dev/tty redirections are guarded with || true (set -e). Password prompts (read -s) are not changed. The helper is defined in apps/_i18n.sh; a program without that file gets a no-op fallback.
- Checks performed: bash -n; nginx-tools-tests/test_saisie_terminal.py (new, static): every interactive read -p / read -e of the Bash programs has tty_ligne on its line; tty_ligne is defined and sets icanon echo echoe; saisie() is defined and used by the i18n context; apps/_menu.py has its own line reader; versions.
- Action required from the user: none.

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

### 2.99.20261111.165500 - Link page question uses /links/

- Motif de la demande: le chemin par defaut de la page de liens devient /links/.
- Detail des modifications: question de l'etape 12 ter : "Creer une page de liens (LittleLink, /links/) maintenant ?".
- Bugs corriges: aucun.
- Garde-fous et cas limites: aucun changement de logique ; seul le texte de la question change.
- Verifications effectuees: nginx-tools-tests/test_nginx_hardening.py lance par le testeur (62 tests, 0 echec, 7 ignores).
- Action requise: aucune.

### 2.98.20261111.140000 - Link page installed automatically when its configuration is valid

- Motif de la demande: nginx-hardening.sh doit installer la page de liens sans question si la configuration est valide.
- Detail des modifications: etape 12 ter. Si une configuration existe, nginx-link-page.sh --check la valide ligne par
  ligne (aucune ecriture). Si elle est valide, nginx-link-page.sh --update --yes installe la page (la confirmation est
  deja donnee par nginx-hardening.sh --update). Si elle est invalide, rien n'est installe et les erreurs sont affichees.
  La question reste posee seulement pour creer le modele quand aucune configuration n'existe.
- Bugs corriges: aucun.
- Garde-fous et cas limites: sans terminal, la creation n'est pas proposee ; en --check, l'etape signale seulement la validite.
- Verifications effectuees: tests de l'ordre (verification avant installation, question avant creation) lances par le testeur.
- Action requise: aucune.


### 2.97.20261111.111000 - Link page step moved before the generic nginx configuration (0f)

- Motif de la demande: la question sur la page de liens doit etre posee avant l'etape 0f (configuration nginx generique),
  pour que la page soit installee avant que cette configuration soit appliquee.
- Detail des modifications:
  - nginx-hardening.sh (2.97.20261111.111000): le bloc 12 ter (page de liens) est deplace avant le bloc 0f. Aucun changement
    de logique : meme question, meme absence d'action sans reponse positive.
  - nginx-tools-tests/test_nginx_link_page.py: test verifiant que 12 ter precede 0f.
- Bugs corriges: aucun.
- Garde-fous et cas limites: la page est installee avec nginx-link-page.sh qui fait son propre nginx -t et restaure l'ancien
  fragment en cas d'echec; a ce moment la configuration generique n'est pas encore appliquee.
- Verifications effectuees: test de l'ordre lance par le testeur; verification de la syntaxe bash.
- Action requise: aucune.


### 2.96.20261111.110000 - Ask whether to create or update the link page

- Motif de la demande: l'administrateur doit pouvoir creer la page de liens depuis nginx-hardening.sh, sans connaitre
  nginx-link-page.sh.
- Detail des modifications:
  - nginx-hardening.sh (2.96.20261111.110000): nouvelle etape 12 ter. Si nginx-link-page.sh est present et qu'une
    configuration existe, la question de la mise a jour est posee au terminal; sinon la question de la creation.
    La creation copie le modele commente (via nginx-link-page.sh --check) et demande de le remplir. Rien n'est installe
    sans reponse positive. En --check, l'etape signale seulement l'etat.
  - nginx-tools-tests/test_nginx_link_page.py: classe HardeningPropose (question avant toute action, sans terminal rien
    n'est lance).
- Bugs corriges: aucun.
- Garde-fous et cas limites: sans terminal (entree non interactive), l'etape ne lance rien et l'indique; la reponse par
  defaut est non; nginx-link-page.sh --update fait sa propre verification (nginx -t) et restaure l'ancien fragment en cas
  d'echec.
- Verifications effectuees: tests de la classe HardeningPropose lances par le testeur; verification de la syntaxe bash.
- Action requise: aucune. Lancer sudo nginx-hardening.sh --update dans un terminal pour recevoir la question.


### 2.95.20261111.090000 - Empty fragment for the link page, included by _odoo-common.conf

- Title: the link page is no longer built here; nginx-hardening.sh only creates the (empty) fragment it includes.
- Reason: the page holds data of a group, which must stay out of the public repository; its configuration is now read by nginx-link-page.sh (1.0).
- Changes: nginx-hardening.sh: liens-publics.conf is created empty with the other generated fragments (step 0f); nginx/snippets/odoo/_odoo-common.conf: include of liens-publics.conf after securite-commune.conf; nginx/VERSION 1.28.20261111.090000.
- Bugs fixed: none.
- Safeguards and edge cases: the fragment holds one comment line, valid in nginx; an existing fragment is never touched; without nginx-link-page.sh the page stays off.
- Checks performed: bash -n nginx-hardening.sh; test_nginx_hardening.
- Action required: none (the page is installed with nginx-link-page.sh --update).

### 2.94.20261110.193238 - Traversal test run once at each --update

- Title: --update checks that the query-string traversal is blocked by nginx, once, after the rules are installed.
- Reason: follows app-health-check.py 2.35, which no longer runs this test hourly.
- Changes: new section "12 bis" (after the real check of the URIs, before the e-mail section 13): with --update only (--check sends no request), runs app-health-check.py --target local --traversal-only, reads its line [OK] or [FAIL], and reports it as pass, fail (with advice on the includes of securite-commune.conf) or a warning if no recognized line comes back. SCRIPT_VERSION updated.
- Bugs fixed: none.
- Safeguards and edge cases: the step is skipped when app-health-check.py is not readable next to this script; the program is stopped after 60 s (timeout); the step changes nothing on the server.
- Checks performed: bash -n nginx-hardening.sh; test_nginx_hardening suite (see the report of the test run).
- Action required: none.

### 2.93.20261109.223000 - Figures for THIS server: workers recommended, PostgreSQL values recomputed even downwards

- Title: step 6 recommends a number of workers for the processors and the memory of this server; step 17 recomputes the values of its own PostgreSQL file for the memory of this server, also downwards.
- Reason: request of the administrator on 2026-11-09: "en DEV, il y a 16 Go, c'est en PROD qu'il y a 32 Go, il faut que les programmes recommandent les meilleures valeurs à configurer dynamiquement".
- Changes: new function workers_conseilles() (min of (2 x CPU) + 1 and what the RAM holds when each process may reach limit_memory_hard 1536 MB, at least 1); step 6: PASS when workers is the recommended value, otherwise an INFO line with the recommendation and its two bounds (the limits of step 6 stay those of the current workers; --workers N shows the calculation before a change); pg_moins_de_disque(): the settings whose sourcefile is 91-nginx-hardening-memory.conf are recomputed for this server (they may go down: a copy of PROD on DEV), a larger value set elsewhere is still kept; comment of the file updated; lang/nginx-hardening.en.po.
- Bugs fixed: symptom: a value written for a larger server would never go down (only raised); diagnosis: our own file was compared like a setting of the administrator; fix: our values are recomputed.
- Safeguards and edge cases: never a lower value than the one the administrator set outside our file; the recommendation of workers is never applied (odoo.conf is never changed).
- Checks performed: test_293_workers_conseilles (PROD 13, DEV 7), test_293_valeurs_de_notre_fichier_recalculees (3276 -> 1638 for 16 GB, work_mem set elsewhere kept), test_nginx_hardening (62 tests) [OK]; ShellCheck 0.11.0 [OK].
- Action required: sudo nginx-hardening.sh --update on DEV and on PROD (each one gets its own figures).

### 2.92.20261109.222500 - Image cache location refused by nginx -t; the real error of nginx -t shown

- Title: the location of the image cache is accepted by nginx; when nginx -t refuses the generic configuration, its error is shown.
- Reason: report of the administrator on 2026-11-09 (DEV, nginx-hardening.sh 2.91 --update): « [FAIL] nginx -t refuse la configuration générique » followed by « syntax is ok / test is successful », and « odoo.conf (ligne 41 xmlrpc_port) : clé inconnue d'Odoo ».
- Changes: nginx/snippets/odoo/_odoo-common.conf: the regular expression of the /web/image location between quotes; nginx/VERSION 1.26.20261109.222500; step 0f: the output of nginx -t on the NEW configuration kept (gen_test) and its [emerg] / [error] lines shown before the files are put back, then the result after the restore; nginx-tools-tests/test_nginx_hardening.py: test_292_regex_avec_accolades_entre_guillemets (every location expression with { must be quoted).
- Bugs fixed:
  - symptom: « nginx -t refuse la configuration générique : retour à l'état précédent » on --update of 2.91; diagnosis: « location ~ ^/(?:[a-z]{2}...) { » without quotes: for nginx the { of {2} opens the block; the test of 2.91 read the configuration with our own parser, not with nginx; fix: the expression between quotes, and a test on every file of nginx/.
  - symptom: the message of the refusal was followed by « syntax is ok » and « test is successful »; diagnosis: nginx -t was run again AFTER the files were put back; fix: the error of the new configuration is shown first.
- Safeguards and edge cases: none new.
- Checks performed: test_292_regex_avec_accolades_entre_guillemets, MoinsDeDisque291 [OK]; ShellCheck 0.11.0 [OK].
- Action required: sudo nginx-hardening.sh --update again (step 0f installs the corrected files).

### 2.91.20261109.221500 - Less disk for nginx and PostgreSQL: image cache, cache in memory, PostgreSQL memory and checkpoints

- Title: nginx keeps the public images of Odoo in its cache, in memory; PostgreSQL gets memory and checkpoints for the memory of the server; step 4 checks what nginx writes to the disk.
- Reason: request of the administrator on 2026-11-09: the LXC container of Odoo 18 CE now has 32 GB; make the scripts set the right parameters so that nginx and PostgreSQL use the disk less (SATA disks, reads of 160 to 230 ms measured by host-perf-audit.py); check the buffers and the cache of the images in nginx-hardening.sh; a cause « waiting for the disk » in the analysis of app-log-live when several workers end together without SQL.
- Changes:
  - nginx/snippets/odoo/_odoo-common.conf: new location for /web/image (with or without a language prefix): proxy_cache odoo_cache, key "$scheme$host$request_uri", proxy_cache_lock, proxy_cache_use_stale updating, same rate limits as location /; NO proxy_cache_valid: only what Odoo declares cacheable (Cache-Control public, max-age) is kept; no proxy_set_header nor add_header (those of the server level apply).
  - nginx/conf.d/odoo-global.conf: proxy_cache_path moved to /dev/shm/nginx-cache (keys_zone 20m, max_size 1g), created by nginx at its start.
  - nginx/VERSION: 1.25.20261109.221500.
  - nginx-hardening.sh: new function nginx_moins_de_disque() (step 4, Odoo only: proxy_buffers, proxy_temp_path, proxy_cache_path in /dev/shm or on the disk, location /web/image with proxy_cache); new function pg_moins_de_disque() and configuration key PG_TUNING (default yes; doc/fr, doc/en templates): step 17 writes conf.d/91-nginx-hardening-memory.conf with shared_buffers (RAM / 10, 4 GB at most), effective_cache_size (RAM / 2), work_mem (16 MB from 16 GB), maintenance_work_mem (RAM / 32, 64 MB to 1 GB), max_wal_size 4 GB, min_wal_size 1 GB, checkpoint_timeout 15 min, checkpoint_completion_target 0.9, wal_compression on; reload; restart of PostgreSQL for shared_buffers asked on a terminal (otherwise said); step 17 now also runs with PG_LOGGING=no when PG_TUNING=yes (logging part skipped); NGINX_HARDENING_MEMINFO for the tests; lang/nginx-hardening.en.po; doc 01-nginx-hardening.md (steps 4, 17).
  - nginx-tools-tests/test_nginx_hardening.py: classes MoinsDeDisque291 (2 tests), test_291_postgres_moins_de_disque; test_283_postgres_desactive with PG_TUNING=no.
- Bugs fixed: none.
- Safeguards and edge cases: a PostgreSQL value is only raised (a larger value set by the administrator is kept, and said in the file); without include_dir 'conf.d' the lines to add are shown; never a restart of PostgreSQL without a yes on a terminal; private images, responses with Set-Cookie and errors are never cached; the cache is lost at each start of the server and fills again; for 32 GB: shared_buffers 3276 MB, inside the 15 % kept outside Odoo by step 6.
- Checks performed: test_nginx_hardening (59 tests) [OK]; test_config_nginx, test_config_defaut, test_cles_modeles [OK]; ShellCheck 0.11.0 [OK].
- Action required: sudo nginx-hardening.sh --update on the Odoo server (step 0f installs the nginx files, step 17 PostgreSQL; answer yes to restart PostgreSQL at a quiet moment), then check step 6 again for the 32 GB.

### 2.90.20261109.215500 - Temporary files of nginx in memory (/dev/shm) instead of the SATA disks

- Title: the temporary files of the responses of Odoo are written in /dev/shm (tmpfs) and bounded to 256 MB per response; step 0c says the room left there.
- Reason: request of the administrator on 2026-11-09: "si NGINX crée des fichiers temporaires, il faudrait les créer dans un ramdisk et les effacer après (comme dans /dev/shm)" (SATA disks, read wait p95 of 160 to 230 ms measured by host-perf-audit.py).
- Changes:
  - nginx/conf.d/odoo-global.conf: proxy_temp_path /dev/shm/nginx-proxy-temp 1 2; proxy_max_temp_file_size 256m; comment (when nginx writes a temporary file: response larger than the buffers of _odoo-common.conf, about 1.1 MB; nginx creates the folder at its start and deletes each file once the response is sent; the uploads, client_body_temp_path, stay on the disk: a restore of a database may be several GB).
  - nginx/VERSION: 1.24.20261109.215500 (installed by step 0f with --update, nginx -t, reload).
  - nginx-hardening.sh: step 0c: room of /dev/shm (NGINX_HARDENING_SHM_DIR for the tests): WARN under 1 GB free (PostgreSQL also uses it), PASS otherwise, WARN when /dev/shm is missing; lang/nginx-hardening.en.po.
  - nginx-tools-tests/test_nginx_hardening.py: class TemporairesEnMemoire290.
- Bugs fixed: none.
- Safeguards and edge cases: the cache (proxy_cache_path, use_temp_path=off) is not concerned; a response above 256 MB is passed on without a temporary file; /dev/shm is emptied at each start of the server and nginx recreates the folder.
- Checks performed: test_nginx_hardening (56 tests), test_config_nginx, test_cdn_realip [OK]; ShellCheck 0.11.0 [OK].
- Action required: sudo nginx-hardening.sh --update on the Odoo servers (step 0f installs odoo-global.conf, nginx -t, reload).

### 2.89.20261109.215000 - Step 4: --update sets worker_connections of nginx on an Odoo server

- Title: on an Odoo server, --update sets worker_connections of nginx to 2048 (configurable) and adds worker_rlimit_nofile when it is missing.
- Reason: request of the administrator on 2026-11-09: "avec l'option --update, peux-tu rajouter cela dans le bon fichier NGINX mais seulement pour le serveur Odoo actuel : worker_connections 2048" (100 to 150 people expected in the live chat).
- Changes: new configuration key WORKER_CONNECTIONS (default 2048; 0 = never changed; doc/fr, doc/en nginx-hardening.conf.example); new function nginx_worker_connections() (step 4, Odoo steps only: never on BigBlueButton): nginx.conf of NGINX_HARDENING_NGINX_DIR copied to the backup folder, worker_connections replaced (or added in the events block, or an events block added), worker_rlimit_nofile (4 x worker_connections, at least 8192) added after worker_processes when absent, nginx -t, reload, the copy put back when nginx -t refuses; step 4 also handles a configuration without worker_connections (nginx's default 512); with --check the warning stays and says that --update sets it; lang/nginx-hardening.en.po; doc 01-nginx-hardening.md (fr, en).
- Bugs fixed: none.
- Safeguards and edge cases: only when the value is under WORKER_CONNECTIONS (a larger value is kept); worker_rlimit_nofile already set is kept; a reload does not cut the connections in progress.
- Checks performed: WorkerConnections289 (value replaced and nofile added; line absent; nginx -t refusing: copy put back, no reload) [OK]; ShellCheck 0.11.0 [OK].
- Action required: sudo nginx-hardening.sh --update on the Odoo servers.

### 2.88.20261109.213000 - Step 8: message of the odoo.conf check well placed; step 6: what is measured

- Title: step 8 shows the line and the key of a finding only when they exist; step 6 says that the measured processes are the workers, the cron threads and gevent.
- Reason: report of the administrator on 2026-11-09 (DEV, nginx-hardening.sh --update): step 8 said « [FAIL] odoo.conf (ligne 0 Odoo refuse ce fichier : ModuleNotFoundError: No module named 'babel') : ».
- Changes: step 8: "-" or "0" read as empty for the line and the key (apps/_odoo_conf_check.py 1.1); step 6: « N processus mesurés : workers, cron, gevent » (was « N workers mesurés » for 3 workers + 2 cron + gevent); lang/nginx-hardening.en.po.
- Bugs fixed: symptom: « [FAIL] odoo.conf (ligne 0 Odoo refuse ce fichier : ...) : »; diagnosis and fix: see apps/_odoo_conf_check.py 1.1.
- Safeguards and edge cases: none new.
- Checks performed: test_odoo_conf_check [OK]; ShellCheck 0.11.0 [OK].
- Action required: none.

### 2.87.20261109.211500 - Step 8: odoo.conf read the way Odoo reads it

- Title: step 8 checks odoo.conf with apps/_odoo_conf_check.py (comment after a value, key twice, wrong type, keys unknown to Odoo, parsing by the Odoo of the server).
- Reason: request of the administrator on 2026-11-09: Odoo refused "limit_memory_soft_gevent = 2147483648 # (2048 Mo" (comment after the value); is there a program that checks the configuration of Odoo, or can one be written.
- Changes: step 6: the suggested lines are printed ready to copy, the size in MB on its own comment line above (before: « limit_memory_soft = N   (N Mo) » on one line, copied with its comment); step 8: apps/_odoo_conf_check.py --tsv, each error as FAIL, each warning as WARN, notes shown, PASS when there is no error (with the command to check alone); lang/nginx-hardening.en.po.
- Bugs fixed: symptom: Odoo did not start after "limit_memory_soft_gevent = 2147483648 # (2048 Mo" was added; diagnosis: Odoo reads its file with configparser.RawConfigParser without inline comments, so the comment stays in the value and the integer cast refuses it; our own readers (apps/_odoo_conf.py) cut at "#" and said nothing; fix: the new check reports a comment after a value as an error, with the line to write.
- Safeguards and edge cases: without python3 or without the module, the step does as before; reads only.
- Checks performed: test_odoo_conf_check (5 tests) [OK]; ShellCheck 0.11.0 [OK].
- Action required: in config.conf, put each comment on its own line (a line that starts with #), then run python3 /opt/rlq-admin-tools/apps/_odoo_conf_check.py /opt/odoo/erplibre/config.conf.

### 2.86.20261109.204500 - Step 6: limits of the live chat (gevent), memory to add, memory nearly used up

- Title: step 6 checks the limits of the gevent process and says how much memory to add when the RAM is short.
- Reason: request of the administrator on 2026-11-09: check limit_memory_soft_gevent / limit_memory_hard_gevent and say what raising them is for (more people chatting at the same time); recommend more memory when the RAM is short.
- Changes: step 6: new local function gevent_valeur() (run.sh production line first, then odoo.conf); WARN when limit_memory_soft_gevent < 2147483648 or limit_memory_hard_gevent < 2684354560 (or not set: Odoo then gives gevent the limits of the workers), with what it is for and the values in bytes, PASS otherwise; memory to add (steps of 1 GB, same reserve and margin) so that every process keeps limit_memory_hard 1536 MB, shown when the RAM is short; WARN when MemAvailable is under 15 % of the memory; lang/nginx-hardening.en.po; doc 01-nginx-hardening.md (fr, en).
- Bugs fixed: none.
- Safeguards and edge cases: nothing is applied; PROD (16 GB, 13 workers): about 8 GB to add (24 GB in all); values given in bytes as odoo.conf wants them.
- Checks performed: test_286_ram_a_ajouter_et_gevent (24576 MB for PROD) and SuggestionMemoire282 [OK]; ShellCheck 0.11.0 [OK].
- Action required: add limit_memory_soft_gevent = 2147483648 and limit_memory_hard_gevent = 2684354560 to odoo.conf, then restart Odoo.

### 2.85.20261109.194500 - Step 6: memory limits in virtual memory, workers recycled at birth detected

- Title: the suggested limit_memory_soft and limit_memory_hard take the virtual memory of the workers into account; a limit under a worker at rest is a failure.
- Reason: report of the administrator on 2026-11-09: PROD workers recycled in a loop after the values of step 6 were applied.
- Changes: new function odoo_worker_memory() (median VmSize and VmSize - VmRSS of the children of the main Odoo process, cgroup of the service; NGINX_HARDENING_PROC_ROOT, NGINX_HARDENING_CGROUP_ROOT, NGINX_HARDENING_WORKER_VMS_MB, NGINX_HARDENING_WORKER_OVERHEAD_MB for the tests); step 6: RAM share per process, worker at rest shown (measured or estimated), suggestion in bytes as written in odoo.conf, worst case in RAM, warning with the largest number of workers that fits; new check of the current limit_memory_soft (run.sh production line first, then odoo.conf): FAIL under a worker at rest, WARN under 1.5 x; the former warning "under 640 MB" removed; lang/nginx-hardening.en.po; doc 01-nginx-hardening.md (fr, en).
- Bugs fixed: symptom: on PROD (13 workers, 16 GB) the Odoo log showed "Worker (N) virtual memory limit (691601408) reached" then "exiting. request_count: 0" several times per second, no worker survived; diagnosis: Odoo compares limit_memory_soft with the VIRTUAL memory of a worker (psutil vms; limit_memory_hard is RLIMIT_AS), and step 6 / the memory risk shared the RAM as if these limits were RAM: 768 MB hard and 652 MB soft were suggested, under the 660 MB of virtual memory of a worker at rest (RSS 250 MB); fix: limit = RAM share + virtual overhead (measured, about 400 MB), limit_memory_soft never under max(1024 MB, 1.5 x a worker at rest), fewer workers suggested when the memory is too short.
- Safeguards and edge cases: nothing is applied (step 6 only suggests); workers not measurable (no root, service stopped): 700 MB at rest and 400 MB of overhead assumed; one busy worker does not change the median.
- Checks performed: SuggestionMemoire282 (DEV 2458 / 2089 MB, PROD 1228 / 1024 MB and 12 workers at most, measurement on a fake /proc) [OK]; ShellCheck 0.11.0 [OK].
- Action required: on PROD, set limit_memory_soft = 1073741824 or more (sent separately: 1342177280 / 1610612736) and restart Odoo; consider 12 workers or fewer.

### 2.84.20261109.190000 - Erase key (^H) in all the questions

- Title: every question of nginx-hardening.sh accepts ^H and ^? as erase key.
- Reason: report of the administrator on 2026-11-09 ("^H" shown in the questions of the programs).
- Changes: the 13 questions "tty_ligne; read -r -p" become "tty_ligne; read -e -r -p" (readline); the SMTP password (read -s, no echo) goes through appliquer_effacements(); fallback appliquer_effacements when apps/_i18n.sh is absent.
- Bugs fixed: symptom: in a question, the erase key showed "3^H^H" and the answer kept the ^H characters; diagnosis: the kernel line mode (stty icanon echoe, put back by tty_ligne) knows ONE erase key only (stty erase, usually ^?), while some terminals (PuTTY, some ssh clients) send ^H; ECHOE does not help when the key is not the erase key; fix: the answers are edited by readline (read -e) or by our own line editor, where ^H AND ^? erase.
- Safeguards and edge cases: without a terminal (pipe), read -e reads like read; the password is still never echoed.
- Checks performed: test_saisie_terminal [OK]; ShellCheck 0.11.0 [OK].
- Action required: none.

### 2.83.20261109.153000 - Persistent systemd journal, PostgreSQL logging, nginx response times, cron threads in step 6

- Title: more traces kept for the investigations: systemd journal kept across restarts, slow PostgreSQL queries and lock waits, nginx and Odoo times in the access logs.
- Reason: request of the administrator on 2026-11-09 ([1]: integrate the suggested logging improvements).
- Changes:
  - Step 6: title "(workers + cron + gevent, mémoire disponible)".
  - Step 11: persistent journal (JOURNAL_PERSISTENT, default 1): /etc/systemd/journald.conf.d/91-nginx-hardening-persistent.conf (Storage=persistent); NGINX_HARDENING_JOURNAL_DIR for the tests.
  - New step 17: PostgreSQL logging (PG_LOGGING, default 1; PG_SLOW_MS, default 2000): log_min_duration_statement, log_lock_waits=on, log_autovacuum_min_duration=250, log_temp_files=10240 in conf.d/90-nginx-hardening-logging.conf, then pg_reload_conf() (no restart); shared_buffers left at 128 MB reported (INFO). NGINX_HARDENING_PSQL for the tests.
  - nginx/conf.d/odoo-global.conf: log_format combined_host ends with rt=$request_time urt="$upstream_response_time" us=$upstream_status (read by app-log-live.py 1.181).
  - lang/nginx-hardening.en.po (31 entries); doc/fr, doc/en nginx-hardening.conf.example (JOURNAL_PERSISTENT, PG_LOGGING, PG_SLOW_MS) and 01-nginx-hardening.md (steps 11, 16, 17).
  - nginx-tools-tests/test_nginx_hardening.py: BaseNginxHardening, class JournalEtPostgres283.
- Bugs fixed: none.
- Safeguards and edge cases: --check changes nothing; the PostgreSQL step is skipped under NGINX_TOOLS_TESTS without NGINX_HARDENING_PSQL (never the real server in a test); a drop-in file of ours only, postgresql.conf is never edited; PG_LOGGING=0 or JOURNAL_PERSISTENT=0 leave the system as it is.
- Checks performed: JournalEtPostgres283 (3 tests), SetupNginxOdoo, ShellCheck 0.11.0 [OK].
- Action required: sudo nginx-hardening.sh --update on DEV then PROD (journal, PostgreSQL, log_format; nginx reloaded).

### 2.82.20261109.100500 - Memory suggestion (step 6): cron threads and gevent counted, reserve outside Odoo

- Title: step 6 shares the memory between the HTTP workers, the cron threads and the gevent process, with a real reserve for PostgreSQL.
- Reason: request of the administrator on 2026-11-09 ("arranger la recommandation dans nginx-hardening.sh afin de rajouter les CRON"): on DEV the suggestion was 5139 MB per worker for 3 workers, but with the 2 cron threads 5 processes at that limit need 25 695 MB for 16 384 MB of memory (app-log-live.py reported the memory risk).
- Changes:
  - Step 6: cron_threads read from --cron-threads, otherwise --max-cron-threads of the production line of run.sh, otherwise max_cron_threads of odoo.conf, otherwise 2; processes = workers + cron + 1 (gevent); reserve = max(15 % of the memory, memory used outside Odoo now); margin = max(512 MB, 10 %); new lines "Tâches planifiées (cron)", "Processus d'Odoo", "Réservé hors Odoo"; the suggestion and the worst case are per process; warning under 640 MB per process; the check of the current limit_memory_hard counts every process.
  - New option --cron-threads N and configuration key MAX_CRON_THREADS (doc/fr and doc/en nginx-hardening.conf.example); CDN key and --dns-refresh cited in the templates; --cdn moved to its alphabetical place in --help.
  - lang/nginx-hardening.en.po: the new messages, the help of --cdn, --cron-threads and --dns-refresh. doc/fr, doc/en 01-nginx-hardening.md: step 6. nginx-tools-tests/test_nginx_hardening.py: class SuggestionMemoire282 (2 tests).
- Bugs fixed:
  - Symptom: "Pire cas (tous les workers à la limite dure en même temps) : 15417 Mo" with 15 419 MB available, while the cron threads and gevent were not counted. Diagnosis: the budget was divided by the HTTP workers only, and the reserve was the memory used at that instant (453 MB) plus 512 MB. Fix: see above (DEV: 2048 MB per process; PROD with 13 workers: 768 MB).
- Safeguards and edge cases: odoo.conf and run.sh are never modified (suggestion only); a cron count that is not a number falls back to 2; a reserve larger than 15 % is kept when more memory is used outside Odoo.
- Checks performed: bash -n, ShellCheck 0.11.0 without warning; test_nginx_hardening.SuggestionMemoire282 [OK]; test_config_defaut and test_cles_modeles [OK].
- Action required: run sudo nginx-hardening.sh --check on DEV and PROD and compare step 6 with the memory risk of app-log-live.py; adjust limit_memory_hard / limit_memory_soft after a test on DEV.

### 2.81.20261106.083524 - Empty ?tags= accepted on the event pages (rule 3 bis)

- Title: securite-commune.conf rule 3 bis now accepts an empty value, ?tags=, as well as the lists of numbers.
- Reason: request of the administrator on 2026-11-06: the dashboard still showed 404 answers (146 bytes, the page of nginx) on /event/page/2?date=all&search=&tags=&type=all&pays=all (referers /event/service-worker.js and /event?date=all).
- Changes:
  - nginx/snippets/securite-commune.conf: rule 3 bis, the value may be empty, or a list in brackets (clear or %5B %5D) of digits, commas, "+", %2B, %2C and %20. Comment updated.
  - nginx/VERSION: 1.23.20261106.083524.
  - nginx-hardening.sh: SCRIPT_VERSION 2.81.20261106.083524; live check "GET /event/page/2?date=all&search=&tags=&type=all -> 2xx/3xx" added.
  - nginx-tools-tests/test_nginx_uri.py: empty value accepted (three URLs), "tags=x", "tags=&tags=stfD" and "tags=[]x" still refused.
- Bugs fixed:
  - Symptom: visitors of the pages 2, 3, 4... of the events list received a 404.
  - Diagnosis: the filter form of the events page sends tags= with no value when no filter is chosen; the look-ahead of rule 3 bis required a bracketed list, so the empty value was refused like a malformed one. The 548 byte 404 of 2.80 had the same cause for the encoded brackets.
  - Fix: the bracketed list of the look-ahead is optional (empty value).
- Safeguards and edge cases: Odoo ignores an empty tags (no literal_eval, so no error 500); every non-empty malformed value stays refused, also when an empty tags= comes first (tags=&tags=stfD).
- Checks performed: test_nginx_uri (10 tests).
- Action required: after the merge, sudo nginx-hardening.sh --update.

### 2.80.20261105.130658 - Encoded brackets of ?tags= accepted on the event pages (rule 3 bis)

- Title: securite-commune.conf rule 3 bis now accepts ?tags=%5B3%5D as well as ?tags=[3].
- Reason: request of the administrator on 2026-11-05: the dashboard of app-log-live.py showed many "404 548" answers on /event/journee-portes-ouvertes-sur-linux-2026-125/track?tags=%5B3%5D (referer service-worker.js) and on /es/event?tags=%5B8%2C%2B13%5D&trk=public_post_comment-text (LinkedIn link).
- Changes:
  - nginx/snippets/securite-commune.conf: rule 3 bis, the brackets may be written "[" "]" or "%5B" "%5D"; the content is still limited to digits, commas, "+", %2B, %2C and %20. Comment updated.
  - nginx/VERSION: 1.22.20261105.130658.
  - nginx-hardening.sh: SCRIPT_VERSION 2.80.20261105.130658; live check "GET /event?tags=%5B35%5D -> 2xx/3xx" added to the checks after installation.
  - nginx-tools-tests/test_nginx_uri.py: FiltreTagsEvenements, encoded legitimate values accepted (the two URLs of the dashboard), encoded malformed values still refused.
- Bugs fixed:
  - Symptom: legitimate visitors of the event track pages received a 404 (548 bytes, the page of nginx).
  - Diagnosis: the Odoo web application service worker (website_event_track) and the links shared on LinkedIn encode the brackets of ?tags=; rule 3 bis wanted the brackets in clear.
  - Fix: the negative look-ahead accepts both forms of the brackets.
- Safeguards and edge cases: Odoo decodes the URL before literal_eval, so [3] and %5B3%5D give the same list and cannot produce an error 500; %5Bx%5D, %5B35%5Dx and a quoted text stay refused; the match is case-insensitive (%5b and %5B).
- Checks performed: test_nginx_uri (10 tests).
- Action required: after the merge, sudo nginx-hardening.sh --update.

### 2.79.20261103.085601 - SofyaBot refused by bot_blocker.conf

- Title: the User-Agent "SofyaBot" (sofya.co) is refused with a 403, like the other commercial crawlers.
- Reason: request of the administrator on 2026-11-03, after nginx-log-audit.sh --investigate of 206.42.109.58 (811 requests in 12 minutes, one burst, score 1/7, verdict "REFUSER LE ROBOT PAR SON NOM"): the robot follows the login, password reset and sign-up links of every blog article.
- Changes:
  - nginx/conf.d/bot_blocker.conf: "SofyaBot" added to the line of commercial crawlers, with its comment.
  - nginx/VERSION: 1.21.20261103.085601.
  - nginx-tools-tests/test_config_nginx.py: test_filtre_a_robots checks the User-Agent.
  - nginx-hardening.sh: SCRIPT_VERSION 2.79.20261103.085601 (the program installs the files of nginx/).
- Bugs fixed: none.
- Safeguards and edge cases: case-insensitive match anywhere in the User-Agent; the name does not appear in a browser User-Agent (test_filtre_a_robots still checks that real browsers and an isolated curl are not blocked).
- Checks performed: test_config_nginx.ConfigNginx.test_filtre_a_robots.
- Action required: after the merge, nginx-hardening.sh --update.

### 2.78.20261102.212810 - Job offer robots (CareerScout, jobs_v1) refused by bot_blocker.conf

- Title: the User-Agents "CareerScout" and "jobs_v1" (job offer aggregator) are refused with a 403, like the other commercial crawlers.
- Reason: request of the administrator on 2026-11-02, after nginx-log-audit.sh --investigate of 192.54.244.135 and 192.54.244.141 (score 1/7 each, banned by the jail nginx-badrequests, then manually at the firewall without expiry). Same block 192.54.244.0/24 (Fiberway / Bullionet, France), same User-Agent "Mozilla/5.0 (X11; Linux x86_64) ... Chrome/120.0 Safari/537.36 (jobs_v1/1.0)" and "Mozilla/5.0 (compatible; CareerScout/1.0)", 150 requests from 2026-09-20 to 2026-10-05, all guesses of job pages (/careers, /jobs, /join-us, /work-with-us, /about/careers..., with and without /en_CA), hence bursts of 404. The robot changes address inside its block, so banning addresses one by one does not stop it; its User-Agent does.
- Changes:
  - nginx/conf.d/bot_blocker.conf: "CareerScout" and "jobs_v1" added to the line of commercial crawlers, with their comment.
  - nginx/VERSION: 1.20.20261102.212810.
  - nginx-tools-tests/test_config_nginx.py: test_filtre_a_robots checks the two User-Agents.
  - nginx-hardening.sh: SCRIPT_VERSION 2.78.20261102.212810 (the program installs the files of nginx/).
- Bugs fixed: none.
- Safeguards and edge cases: case-insensitive match anywhere in the User-Agent; neither name appears in a browser User-Agent (test_filtre_a_robots still checks that real browsers and an isolated curl pass). /robots.txt stays readable. app-log-live.py reads the list from /etc/nginx/conf.d/bot_blocker.conf, so these 403 are labelled [BOT] (checked with bot_blocked_re()). 140.82.7.85 (Vultr, same kind of job page guesses on 2026-10-15) sends a plain Chrome User-Agent: it is not caught by this rule; the jail nginx-badrequests banned it within 6 s.
- Checks performed: test_config_nginx.ConfigNginx.test_filtre_a_robots [OK] (NGINX_ODOO_DIR=nginx/).
- Action required: after the merge, nginx-hardening.sh --update. Then, if wanted: nginx-log-audit.sh --unban 192.54.244.135, --unban 192.54.244.141 and --unban 140.82.7.85.

### 2.77.20261102.205839 - Webz.io robot (webzio) refused by bot_blocker.conf

- Title: the User-Agent "webzio" (Webz.io, commercial collector of web data) is refused with a 403, like the other content harvesters.
- Reason: request of the administrator on 2026-11-02, after nginx-log-audit.sh --investigate 82.166.33.79 (manual ban of 2026-09-27, score 3/7). The address, at an Israeli access provider (Cellcom / Barak), sent 15 requests in one burst on 2026-09-27 at 19:48: 12 feed names (/rss, /feed, /atom.xml, /index.rss...) in 10 s, alternating "webzio (+https://webz.io/bot.html)", python-requests (already refused, 9 x 403) and a Chrome User-Agent. Nothing sensitive was requested; the robot declares its name, so refusing it by User-Agent is more fitting than a permanent firewall ban of an access-provider address that will be reassigned.
- Changes:
  - nginx/conf.d/bot_blocker.conf: "webzio" added to the line of AI training / content harvesting robots, with its comment.
  - nginx/VERSION: 1.19.20261102.205839.
  - nginx-tools-tests/test_config_nginx.py: test_filtre_a_robots also checks "webzio (+https://webz.io/bot.html)".
  - nginx-hardening.sh: SCRIPT_VERSION 2.77.20261102.205839 (the program installs the files of nginx/).
- Bugs fixed: none.
- Safeguards and edge cases: case-insensitive match anywhere in the User-Agent, like the other names of the line; "webzio" does not appear in browser User-Agents (test_filtre_a_robots still checks that real browsers and an isolated curl pass). /robots.txt stays readable by the robot ($is_bad_bot_enforced exemption). app-log-live.py reads the list from /etc/nginx/conf.d/bot_blocker.conf at start, so these 403 are labelled [BOT] without a change of the program (checked with bot_blocked_re() on the new file); its built-in list BOT_BLOCKED_DEFAULT, used only when the file is absent, is left unchanged to avoid a conflict with the open pull request of app-log-live 1.153. The Chrome User-Agent of the same robot is not caught by this rule (no way to tell it from a browser by name).
- Checks performed: test_config_nginx.ConfigNginx.test_filtre_a_robots [OK] (NGINX_ODOO_DIR=nginx/). The other failures of test_config_nginx with that folder come from the site files absent from the repository (vhosts, cdn-realip.conf, robots-disallow.conf, uri-desactivees.conf) and are identical without this change.
- Action required: after the merge, nginx-hardening.sh --update (installs bot_blocker.conf, nginx -t and reload). Then, if wanted, lift the firewall ban: nginx-log-audit.sh --unban 82.166.33.79.

### 2.76.20261102.104500 - Dated [temporaire] entries and 15-minute check

- Title: a white list entry marked [temporaire AAAA-MM-JJ HH:MM:SS] is valid until that local date and time, then removed from nginx and fail2ban. The check runs every 15 minutes.
- Reason: the administrator asked to keep the temporary option, with an explicit expiry date instead of a 4-week counter, and to check every 15 minutes instead of 10.
- Changes:
  - apps/_listes.sh and apps/_listes.py (version 1.7): option [temporaire DATE TIME] read; listes_maintenant / maintenant (NGINX_TOOLS_MAINTENANT for tests); entries past their date, or without a valid date, are left out of the effective list.
  - nginx-hardening.sh: --dns-refresh checks DNS names and [temporaire] entries; the state file holds a signature of the effective list, so an expired entry triggers a full --update just like an address change. Cron every 15 minutes (installed while there are DNS names or [temporaire] entries). Step 12 function temporaires_verifier warns about expired and invalid entries.
  - doc/fr and doc/en nginx-tools-white-list.conf.example: format of the option and the DNS names.
- Bugs fixed: none.
- Safeguards and edge cases:
  - An option without a valid date is ignored and reported, never trusted indefinitely.
  - The date comparison uses the local time of the server.
  - When a name does not resolve, the last known addresses stay, as before.
- Checks: nginx-tools-tests/test_listes.py (dated entries, Python and bash agree at two dates); test_dns_blanche.py; test_alignement, test_nginx_hardening, test_ban_gate: OK.
- Action required: none. Write the expiry on the lines that should expire, for example [temporaire 2026-11-30 18:00:00]. Run nginx-hardening.sh --update once after the merge to install the 15-minute cron.

### 2.75.20261102.102600 - DNS names in the white list (dynamic addresses)

- Title: a white list entry can be a DNS name (for example a DynDNS name) instead of an IP address. The addresses it resolves to are kept in nginx and fail2ban up to date.
- Reason: a team member's home address changes. Writing the name avoids editing the configuration each time the address changes.
- Changes:
  - nginx-hardening.sh: new options --dns-refresh (resolves the names; runs a full --update only when an address changed; silent otherwise). Functions dns_etat, dns_ips_du_nom, dns_resoudre, dns_rafraichir, dns_cron_installer. generer_equipe writes the resolved addresses, never the name. verifier_ignoreip includes them in the fail2ban ignore list.
  - Step 12 installs /etc/cron.d/nginx-tools-dns (every 10 minutes) while the white list has names, and removes it otherwise.
  - State file: /var/lib/nginx-tools/white-list-dns.tsv (NAME TAB ADDRESS ADDRESS...), overridable with NGINX_TOOLS_DNS_STATE; resolver overridable with NGINX_TOOLS_GETENT (tests).
  - apps/_listes.sh: listes_nom_dns, listes_noms_dns. Address functions still accept only IP addresses.
  - doc/fr and doc/en nginx-tools-white-list.conf.example: description of DNS names.
- Bugs fixed: none.
- Safeguards and edge cases:
  - nginx never receives a name (its allow and geo directives require an address): an unresolved name keeps its last known addresses; a DNS outage does not remove access.
  - --dns-refresh restores the previous state if the full --update fails, so the next run retries.
  - fail2ban receives the resolved addresses rather than the name, so it does not depend on how fail2ban itself refreshes names.
  - A change is applied within about 10 minutes; the log is /var/log/nginx-tools-dns.log.
- Checks: nginx-tools-tests/test_dns_blanche.py (names read by Python and bash, change detection, outage fallback, --check writes nothing, option present); test_listes, test_alignement, test_ban_gate, test_nginx_hardening: OK.
- Action required: none, unless a white list entry should be a DNS name: write the name in place of the IP.

### 2.72.20261101.234513 - Visitor's security.txt file no longer refused (/.well-known/security.txt)

- Title: /.well-known/security.txt (RFC 9116) is served by Odoo again instead of a 404 from nginx; the other files of /.well-known/ stay refused.
- Reason: on 2026-11-01 a visitor requested /.well-known/security.txt (a standard file for reporting security issues). nginx refused it with a 404 and counted it as a probe in blocked-probes.log. On the DEV server nginx-catchall logged this address 16 times between 2026-10-04 and 2026-10-28; it was never banned, but the counts were false.
- Changes:
  - nginx/snippets/securite-commune.conf, rule "location ~ /\." (hidden files): exemption of the exact path /.well-known/security.txt only.
  - nginx/snippets/securite-commune.conf, rule 5 (extensions .txt, .php, .env, etc.): the same exact path is excluded from the lookahead.
  - nginx/VERSION: 1.18.20261101.234513.
  - nginx-tools-tests/test_config_nginx.py: test_security_txt_seul_fichier_de_well_known_autorise (security.txt allowed; /.well-known/x.txt, /.well-known/.env, /.well-known/security.txt.php, /config.txt and /.well-known/security.txt.bak still refused).
  - nginx-hardening.sh: SCRIPT_VERSION 2.72.20261101.234513 (the program installs the files of nginx/).
- Bugs fixed: symptom: 404 and false probe counts for /.well-known/security.txt. Diagnosis: two rules refuse it, the hidden-files rule (any "/." in the path) and the extension rule (".txt"). Fix: an exemption limited to this one path in both rules.
- Safeguards and edge cases: the exemption is an exact path (no prefix), so /.well-known/.env, /.well-known/x.txt or /.well-known/security.txt.php stay refused. The file itself is not created by this change: a site without security.txt still answers 404, through Odoo.
- Checks performed: test_config_nginx, class RegleWordPress: 4 tests OK, with NGINX_ODOO_DIR pointing to nginx/. The module as a whole gives the same 4 failures and 8 errors as before this change, because the private nginx-odoo configuration is not in the repository (checked by running the tests before and after the change). bash -n on nginx-hardening.sh.
- Action required: run sudo nginx-hardening.sh --update on each Odoo server to deploy the new securite-commune.conf (review the diff, then confirm). Then curl -sI https://<domaine>/.well-known/security.txt must no longer return a 404 from nginx (Odoo's answer, 404 or 200, is normal). Creating a security.txt file on the site is a separate decision, not part of this change.
### 2.74.20261101.231500 - Retour arrière : écho et effacement rétablis avant chaque réponse

- Title: each question of nginx-hardening.sh (yes/no, menus, text answers, the SMTP setup question) restores echo and erase first.
- Reason: Request of the administrator: in nginx-hardening.sh, at the prompt "Faire le setup du courriel (relais SMTP) maintenant ? [o/N] :", the Backspace key shows "d^H^H^H^H" and erases nothing. The same problem can hit every program that asks a question, so every interactive prompt of the Bash and Python programs must be checked and fixed.
- Changes: tty_ligne; placed before the 13 interactive reads (read -r -p) of the program: confirmation helper, menus, the SMTP setup, test mail, GENERIC plan, fail2ban SQLi change, 404 refusals, rename, restore, time zone. Fallback definition of tty_ligne after the loading of apps/_i18n.sh.
- Bugs fixed: symptom: at "Faire le setup du courriel (relais SMTP) maintenant ? [o/N] :" the Backspace key showed "d^H^H^H^H" instead of erasing. Diagnosis: ECHOE off on the terminal (see apps/_i18n.py 1.22). Fix: tty_ligne before the read.
- Safeguards and edge cases: Without a terminal (pipe, cron, stdin not a tty): nothing is changed, the programs behave as before. Stdin and /dev/tty redirections are guarded with || true (set -e). Password prompts (read -s) are not changed. The helper is defined in apps/_i18n.sh; a program without that file gets a no-op fallback. The password read (read -r -s) is not changed.
- Checks performed: bash -n; nginx-tools-tests/test_saisie_terminal.py (new, static): every interactive read -p / read -e of the Bash programs has tty_ligne on its line; tty_ligne is defined and sets icanon echo echoe; saisie() is defined and used by the i18n context; apps/_menu.py has its own line reader; versions.
- Action required from the user: none. Version 2.73 -> 2.74.

### 2.73.20261101.214534 - --cdn on the command line is saved to the configuration file

- Title: --update --cdn none|cloudflare writes CDN= in /etc/default/nginx-hardening.conf, so the choice survives the next --update.
- Reason: after 2.72, the file key is read, but nothing wrote it: the administrator still had to add CDN=cloudflare by hand on each server.
- Changes:
  - nginx-hardening.sh: variable CDN_A_ENREGISTRER, set when --cdn is given on the command line with a valid value (none or cloudflare). An invalid value is not saved (step 12c still refuses it).
  - State file (same logic as TIMEZONE): the old CDN= lines are removed, then CDN=<value> is written with the SETUP_* lines. The other lines (options, LANGUAGE) are kept.
  - nginx-tools-tests/test_cdn_config.py: 2 static tests added (write logic, version updated).
  - Version 2.73 (minor, +0.1).
- Bugs fixed: none.
- Safeguards and edge cases:
  - Without --cdn on the command line, the file is not changed (the value read from the file or the default is used as before).
  - --cdn invalid: nothing written, cdn-realip.conf not modified.
  - --check (CHECK_ONLY) writes nothing, as before.
- Checks: test_cdn_config (6 tests); bash -n OK. The writing itself was not run on a real server.
- Action required: none. To set cloudflare permanently, run --update --cdn cloudflare once on each server.

### 2.72.20261101.213902 - CDN setting read from the configuration file

- Title: the key CDN of /etc/default/nginx-hardening.conf (or ~/.nginx-hardening.conf) is now read, so --update no longer needs --cdn cloudflare.
- Reason: after an --update without --cdn cloudflare, cdn-realip.conf was regenerated with 0 range (CDN "none"), and nginx again saw the Cloudflare nodes instead of the visitors. Setting CDN=cloudflare in the configuration file had no effect.
- Diagnosis: config_lire loads every key of the file into CFG, but the script only copies the keys it declares with config_defaut. CDN was not declared, so the file value was ignored and the default "none" was used.
- Changes:
  - nginx-hardening.sh: config_defaut CDN CDN --cdn texte, placed right after config_lire. A command-line --cdn still wins, as with the other options.
  - nginx-tools-tests/test_cdn_config.py (new): 4 tests reproducing the script sequence in a temporary directory (CDN in the file applied; no key keeps none; no file keeps none) and a static check of the order.
  - Version 2.72 (minor, +0.1).
- Bugs fixed: symptom: CDN=cloudflare in the file ignored. Diagnosis and fix as above.
- Safeguards and edge cases:
  - An invalid value in the file (for example CDN=akamai) is refused by step 12c, as on the command line; cdn-realip.conf is not modified.
  - Empty value or missing key: the default "none" is kept.
  - The key is not written by --update; only the reading is added.
- Checks: test_cdn_config (4 tests); test_cdn_realip and test_nginx_hardening unchanged; bash -n OK; the isolated sequence was reproduced before the change (CDN stayed none with the key present).
- Action required: to make cloudflare permanent, add the line CDN=cloudflare to /etc/default/nginx-hardening.conf on each server (after this version is installed). Until then, keep --cdn cloudflare on the command line.

### 2.71.20261101.181555 - Odoo event tickets without parameters answer 404 (--update)

- Title: /event/<id>/my_tickets requested without parameters now gets a 404 from nginx instead of a 500 from Odoo.
- Reason: on 2026-11-01 Odoo 18 CE logged a TypeError for GET /event/119/my_tickets (requested by cache.google.com). The request had no registration_ids nor tickets_hash, so the controller raised an exception and the visitor got a 500.
- Changes:
  - nginx/snippets/odoo/_odoo-common.conf: new location ~ for ^(/xx_XX)?/event/<id>/my_tickets$, placed before location /. If the query string is empty, "return 404"; otherwise the request goes to Odoo with the same proxy headers as location /.
  - nginx/VERSION: 1.17.20261101.181555.
  - nginx-hardening.sh: SCRIPT_VERSION 2.71.20261101.181555. The file is deployed by --update (step 0f, with confirmation, backup and nginx -t).
  - nginx-tools-tests/test_config_nginx.py: test_billets_sans_parametres_renvoient_404.
- Bugs fixed: symptom: 500 and an Odoo traceback for each unparameterized request. Diagnosis: EventController.event_my_tickets() requires registration_ids and tickets_hash; Odoo does not check them before the call. Fix: nginx answers the malformed request itself.
- Safeguards and edge cases: only the exact path /event/<digits>/my_tickets is matched; the 404 happens only when $args is empty; valid links with parameters are unchanged. The location declares its own proxy_set_header lines, so the inheritance problem described in location / does not apply. No ban is involved, so the CDN rules do not apply.
- Checks: test_config_nginx (new test). Structural check only; nginx -t must be run on the server after --update.
- Action required: run sudo nginx-hardening.sh --update on each Odoo server, review the diff shown for /etc/nginx/snippets/odoo/_odoo-common.conf, confirm, then test: curl -sI https://<domaine>/event/119/my_tickets must return 404.

### 2.70.20261101.174000 - Visitor address behind Cloudflare (option --cdn cloudflare)

- Title: with --cdn cloudflare, nginx takes the visitor's real address from the CF-Connecting-IP header, only for connections coming from Cloudflare's published ranges.
- Reason: on 2026-11-01, nginx-log-audit.sh saw only the Cloudflare node address. The nginx-badrequests jail banned that node on ordinary 404 and 30x responses, which blocked a real visitor behind the same node. The fix must make fail2ban and the rate limits see the visitor, not the node.
- Changes:
  - nginx-hardening.sh: new option --cdn (none by default, or cloudflare), read from the configuration like the other options (CDN key). New function generer_cdn (content of the file). New step 12c that writes /etc/nginx/snippets/cdn-realip.conf, tests nginx -t, applies it, and restores the previous version if nginx -t refuses it. cdn-realip.conf is added to the fragments created empty by fragments_generes_assurer.
  - nginx/cdn/cloudflare-ips.txt (new): the Cloudflare ranges (21 CIDR, IPv4 and IPv6). IPv4 block 104.16.0.0/12 (CLOUDFLARENET, RDAP) replaces 104.16.0.0/13 and 104.24.0.0/14, which did not cover 104.28.x.x (found by a test on 104.28.221.220).
  - nginx/conf.d/odoo-global.conf: include of cdn-realip.conf in the http context.
  - nginx-tools-tests/test_cdn_realip.py (new): 6 tests (valid ranges, generated output with and without CDN, include, fragment list, option read and checked).
- Bugs fixed: none in code. The problem is the missing feature described above (CF-Connecting-IP not used).
- Safeguards and edge cases:
  - The header is believed only from the listed ranges: a client outside Cloudflare cannot forge it.
  - Without --cdn (default), cdn-realip.conf contains only comments: $remote_addr is unchanged, no behaviour change.
  - An unknown --cdn value is refused before anything is written.
  - An existing file is replaced only after nginx -t accepts the new version; otherwise the previous content is restored.
  - Behind Cloudflare, the team and shared-network lists (geo blocks on $remote_addr) now compare visitor addresses, which is the intended effect.
- Checks: nginx-tools-tests test_cdn_realip (6 tests, OK); test_config_nginx and test_nginx_hardening (78 tests, OK, same result as main); generer_cdn output checked by hand for both values; syntax checked with bash -n.
- Not verified here: the end-to-end run (nginx -t and reload on a real server with a real Cloudflare connection); the ranges must be checked against https://www.cloudflare.com/ips-v4 and ips-v6 before merge, because the sandbox could not reach those pages.
- Action required: after merge, run nginx-hardening.sh --update --cdn cloudflare on the production server (the CDN key can also be set in /etc/default/nginx-hardening.conf). Check with a few requests that nginx-log-audit.sh shows visitor addresses, not 104.16.x.x / 172.64.x.x nodes.

### 2.69.20261031.191441 - No 404 question when the list of refused URIs does not change - No 404 question when the list of refused URIs does not change

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

## nginx-link-page.sh

### 1.9.20261111.165500 - English template, /links/ as default path, auto-creation checked

- Motif de la demande: le modele de configuration par defaut doit etre en anglais, et le chemin par defaut doit etre
  /links/ au lieu de /liens/.
- Detail des modifications:
  - nginx-link-page.conf.example: entierement en anglais (commentaires, exemples, valeurs de depart My group, Facebook
    page, YouTube channel). Chemins par defaut : PAGE_1_PATH=/links/, PAGE_1_DIR=/var/www/links, PAGE_2 /links2/.
    Cles et structure inchangees ; le modele decommente reste valide.
  - nginx-link-page.sh (1.9.20261111.165500): texte d'aide des chemins ; le chemin de page se nomme /links/.
  - nginx-hardening.sh (2.99.20261111.165500): question de l'etape 12 ter pour /links/.
- Bugs corriges: aucun dans le script. Verification : sans fichier de configuration, --update cree le modele (copie dans
  /etc/default si le dossier est accessible en ecriture, sinon dans ~/.nginx-link-page.conf), puis s'arrete avec un
  avertissement. Un fichier deja present (meme vide ou modele non rempli) n'est jamais recree : il est lu et les erreurs
  de remplissage sont affichees.
- Garde-fous et cas limites: les chemins existants (/liens/ ...) restent valides : seul le modele et la question changent.
- Verifications effectuees: bash -n ; py_compile ; tests de nginx-tools-tests/test_nginx_link_page.py et
  test_nginx_hardening.py (une fois lances) ; execution manuelle sans configuration (cas A : copie dans ~/.nginx-link-page.conf, code 1).
- Action requise: pour un nouveau serveur, le chemin sera /links/. Pour garder /liens/, l'ecrire dans la configuration
  (PAGE_1_PATH=/liens/).

### 1.8.20261111.163800 - Pages per language, automatic language choice from the browser

- Motif de la demande: publier la page de liens en francais et en anglais, et choisir la langue par defaut selon le
  navigateur du visiteur, sans JavaScript (la politique CSP l'interdit).
- Detail des modifications:
  - nginx-link-page.sh (1.8.20261111.163800): PAGE_n_LANGUAGES=fr, en, fr,en ou en,fr. La premiere langue est servie a
    la racine de la page (/liens/) ; l'autre dans un sous-dossier (/liens/en/). Chaque langue a son propre index.html,
    ses ressources et son bouton vers l'autre langue.
  - Detection : nginx lit l'en-tete Accept-Language sur la racine seulement. Si le navigateur demande d'abord l'autre
    langue, il est redirige (302) vers son dossier. Sinon la racine reste la langue par defaut. L'en-tete
    Vary: Accept-Language evite qu'un cache serve la mauvaise langue.
  - Textes anglais facultatifs : SITE_TITLE_EN, SITE_HEADING_EN, SITE_DESCRIPTION_EN, SITE_FOOTER_EN, PAGE_n_TITLE_EN,
    LINK_n_LABEL_EN. Sans texte anglais, le texte francais est repris.
  - Le dossier de la page est copie d'un bloc (la racine et les sous-dossiers) ; --update retire aussi les anciens
    sous-dossiers en et fr.
  - nginx-link-page.conf.example: PAGE_n_LANGUAGES et les textes anglais documentes.
  - Tests: langues invalides refusees ; deux langues installees avec textes anglais, bouton entre langues et redirection
    Accept-Language dans le fragment nginx.
- Bugs corriges: aucun.
- Garde-fous et cas limites: valeurs de langue limitees a fr et en ; un en-tete Accept-Language absent donne la langue
  par defaut ; seule la racine est redirigee (pas de boucle entre les deux langues) ; les textes anglais sont
  echappes comme les textes francais.
- Verifications effectuees: bash -n ; py_compile des tests ; tests de nginx-tools-tests/test_nginx_link_page.py.
- Action requise: aucune pour une configuration existante (une seule langue par defaut). Pour activer les deux langues,
  ajouter PAGE_1_LANGUAGES=fr,en et les textes anglais voulus, puis relancer nginx-link-page.sh --update --yes.

### 1.7.20261111.162600 - Base for relative addresses taken from the server certificate

- Motif de la demande: un serveur n'a qu'un seul domaine ; SITE_BASE_URL doit donc etre facultatif et le domaine doit
  venir du certificat deja utilise sur le serveur.
- Detail des modifications:
  - nginx-link-page.sh (1.7.20261111.162600): sans SITE_BASE_URL, la base est le dossier unique de
    /etc/letsencrypt/live/ (certbot nomme chaque dossier d'apres le domaine du certificat) : https://DOMAINE/.
    Plusieurs dossiers : pas de base, les chemins relatifs sont refuses avec un message clair.
    Une SITE_BASE_URL declaree reste prioritaire. Le dossier peut etre change par
    NGINX_LINK_PAGE_LETSENCRYPT_DIR (utile aux tests).
  - La sortie indique la base utilisee et sa source (SITE_BASE_URL ou certificat).
  - nginx-link-page.conf.example: SITE_BASE_URL decrite comme facultative.
  - Tests: base prise dans un certificat unique ; base refusee avec deux certificats ; SITE_BASE_URL prioritaire.
- Bugs corriges: aucun.
- Garde-fous et cas limites: un dossier sans fullchain.pem est ignore ; le domaine du certificat est le nom
  primaire (pour un certificat exemple.org, la base sera https://exemple.org/, sans www) ;
  un serveur qui heberge aussi un autre certificat (courriel, par exemple) doit declarer SITE_BASE_URL.
- Verifications effectuees: bash -n ; py_compile des tests ; tests de nginx-tools-tests/test_nginx_link_page.py.
- Action requise: aucune si le serveur n'a qu'un certificat. Sinon, declarer SITE_BASE_URL dans
  /etc/default/nginx-link-page.conf.

### 1.6.20261111.144200 - Relative addresses resolved from SITE_BASE_URL

- Motif de la demande: ne plus repeter le domaine du site dans chaque adresse (ex. https://www.exemple.org/evenement)
  et pouvoir changer de nom de serveur sans toucher aux liens.
- Detail des modifications:
  - nginx-link-page.sh (1.6.20261111.144200): nouvelle cle SITE_BASE_URL (facultative, https:// seulement). Les valeurs
    relatives de SITE_LOGO_URL, LINK_n_URL, LINK_n_ICON et LINK_n_ICON_DARK sont resolues par la fonction resoudre_url
    avant la validation : /event/ devient SITE_BASE_URL/event/. Les adresses https:// et les icones builtin:NOM ne changent pas.
  - nginx-link-page.conf.example: cle SITE_BASE_URL commentee et regle des adresses mise a jour.
  - Tests: chemin relatif sans base refuse ; chemins dangereux refuses (//, javascript:, .., http://) ; base http:// refusee ;
    chemins relatifs resolus lors de l'installation.
- Bugs corriges: aucun.
- Garde-fous et cas limites: un chemin relatif sans SITE_BASE_URL est refuse ; // (adresse sans schema), deux points
  (schema), .. et http:// sont refuses ; le resultat doit passer la meme validation https:// qu'une adresse complete.
- Verifications effectuees: bash -n ; py_compile des tests ; tests de nginx-tools-tests/test_nginx_link_page.py.
- Action requise: aucune pour une configuration existante. Pour utiliser les chemins relatifs, ajouter SITE_BASE_URL
  dans /etc/default/nginx-link-page.conf puis relancer nginx-link-page.sh --update --yes.

### 1.5.20261111.143000 - Page variants (brand buttons, avatar shape, accent colour) and theme switch page

- Motif de la demande: l'utilisateur veut comparer des variantes de la page de liens et pouvoir changer de theme depuis
  la page web elle-meme, avec un nouveau bouton.
- Detail des modifications:
  - nginx-link-page.sh (1.5.20261111.143000): nouvelles cles par page, validees a --check.
    PAGE_n_BUTTONS=default|brand : brand applique les boutons aux couleurs Facebook, LinkedIn et YouTube lorsque l'icone
    est integree (builtin:facebook, builtin:linkedin, builtin:youtube) et que la classe existe dans css/brands.css.
    PAGE_n_AVATAR=none|soft|rounded : forme du logo (classe avatar--none, avatar--soft ou avatar--rounded).
    PAGE_n_ACCENT=#RRGGBB : couleur des boutons par defaut, ecrite dans css/accent.css (vide : aucune couleur ajoutee).
    PAGE_n_SWITCH=yes|no : yes genere autre.html avec l'autre theme (sombre pour light et auto, clair pour dark) et
    ajoute sur chaque page un bouton vers l'autre. Aucun script n'est utilise : la politique CSP de la page interdit
    tout JavaScript, la bascule est donc un lien vers une seconde page complete.
  - genere_index accepte le nom du fichier, la cible et le libelle du bouton de bascule ; les libelles suivent
    SITE_LANGUAGE (fr ou en).
  - La suppression des anciennes pages (--update) retire aussi autre.html ; l'installation copie tous les fichiers .html
    de la page.
  - nginx-link-page.conf.example: cles commentees avec leurs valeurs par defaut (default, none, vide, no).
  - Tests: validations refusees (BUTTONS, AVATAR, ACCENT, SWITCH), validations acceptees, installation avec marque,
    avatar, accent et bascule. Le stub de git ecrit maintenant un css/brands.css contenant .button-faceb.
- Bugs corriges: aucun.
- Garde-fous et cas limites: valeurs inconnues refusees avant toute installation ; une couleur qui n'est pas #RRGGBB
  est refusee (aucune valeur libre n'entre dans le CSS) ; sans PAGE_n_SWITCH=yes, autre.html n'est pas cree ; une
  icone externe (https) garde le bouton par defaut en mode brand.
- Verifications effectuees: bash -n sur nginx-link-page.sh ; py_compile des tests ; tests de nginx-tools-tests/
  test_nginx_link_page.py lances par le testeur.
- Action requise: aucune pour une configuration existante (valeurs par defaut inchangees). Pour activer une variante,
  ajouter les cles voulues dans /etc/default/nginx-link-page.conf puis relancer nginx-link-page.sh --update --yes
  (ou nginx-hardening.sh --update).


### 1.4.20261111.140000 - Redirect /liens to /liens/ and validate the configuration before installing

- Motif de la demande: l'adresse sans le / final (/liens) donnait une erreur 404, car la location ne couvrait que /liens/.
- Detail des modifications: pour chaque page active, le fragment liens-publics.conf contient aussi une location exacte
  (location = /liens) qui redirige en 301 vers /liens/. La page est donc atteinte avec ou sans le / final.
- Bugs corriges: 404 sur /liens (symptome) ; location ^~ /liens/ ne couvre pas /liens (diagnostic) ; redirection exacte
  ajoutee (correction).
- Garde-fous et cas limites: le chemin reste obligatoirement avec / final dans la configuration (validation inchangee) ;
  les adresses /liens et /liens/ sont toutes deux servies.
- Verifications effectuees: tests d'installation (location = /liens et return 301) lances par le testeur.
- Action requise: relancer nginx-hardening.sh --update (ou nginx-link-page.sh --update) pour regenerer le fragment.


### 1.3.20261111.105500 - Configuration created automatically when none exists

- Motif de la demande: l'utilisateur ne doit pas avoir a lancer --init. Sans fichier de configuration, le programme doit
  creer lui-meme la configuration a partir du modele, puis indiquer quoi remplir.
- Detail des modifications:
  - nginx-link-page.sh (1.3.20261111.105500): si aucun fichier n'est lu et qu'aucun -c n'est donne, le modele est copie
    dans /etc/default/nginx-link-page.conf (si ce dossier est accessible en ecriture), sinon dans ~/.nginx-link-page.conf.
    Le programme s'arrete ensuite avec un avertissement, sans rien installer (code de sortie 1).
  - --init reste disponible mais n'est plus necessaire.
  - nginx-link-page.conf.example: procedure de remplissage mise a jour (la premiere etape cree le fichier).
  - Tests: la creation automatique, l'absence de creation pour --version et --help, et l'absence de creation pour un
    fichier donne avec -c.
- Bugs corriges: aucun.
- Garde-fous et cas limites: un -c absent n'est jamais cree (une erreur est affichee); --version et --help ne creent rien;
  le fichier cree n'est jamais ecrase (--init refuse un fichier existant); rien n'est installe au premier passage.
- Verifications effectuees: tests unitaires de nginx-tools-tests/test_nginx_link_page.py lances par le testeur; execution
  manuelle sans configuration (copie dans ~/.nginx-link-page.conf, code de sortie 1).
- Action requise: aucune de plus que de remplir le fichier cree, puis relancer --check et --update --yes.


### 1.2.20261111.104500 - Commented template, --init, and a hint when no configuration exists

- Motif de la demande: lancer --check sans fichier de configuration donnait trois erreurs sans indiquer quoi faire. Il faut
  un modele commente, avec des exemples et la procedure de remplissage.
- Detail des modifications:
  - nginx-link-page.conf.example: entierement commente (aucune cle active), avec la procedure de remplissage rapide, les
    regles, les icones courantes et des exemples pour chaque bloc (contenu partage, liens, pages).
  - nginx-link-page.sh (1.2.20261111.104500): option --init, qui copie le modele dans /etc/default/nginx-link-page.conf
    (ou dans le fichier donne avec -c). Il n'ecrase jamais un fichier existant et indique quand sudo est necessaire.
  - Sans fichier de configuration, --check ajoute une astuce qui indique la commande --init.
  - nginx-tools-tests/test_nginx_link_page.py: le modele commente doit etre refuse avec un message clair; le modele
    decommente doit etre valide; --init cree le fichier puis refuse de l'ecraser; l'astuce est affichee sans configuration.
- Bugs corriges: aucun. Le modele precedent, qui contenait des valeurs actives d'exemple, pouvait etre pris pour une
  configuration reelle; il est remplace par un modele entierement commente.
- Garde-fous et cas limites: --init refuse un fichier existant; le modele est lu depuis le dossier du programme, donc
  --init ne fonctionne que si le depot est present; les lignes commentees (#CLE) sont ignorees par le lecteur de
  configuration; le modele decommente est verifie par les tests.
- Verifications effectuees: tests unitaires de nginx-tools-tests/test_nginx_link_page.py lances par le testeur; execution
  manuelle de --check sans configuration (message et code de sortie 1), de --init (creation) et de --help (ordre des options).
- Action requise: sur le serveur, lancer sudo nginx-link-page.sh --init, puis remplir /etc/default/nginx-link-page.conf
  (decommenter les lignes utiles), puis --check, puis sudo nginx-link-page.sh --update --yes.


### 1.1.20261111.093000 - Several link pages at once, one engine per page, shared content

- Motif de la demande: pouvoir installer plusieurs pages de liens (LittleLink maintenant, LinkStack ou d'autres plus tard)
  pour les comparer, avec des adresses differentes (/liens/, /liens2/...). Le contenu du groupe (titres, liens, logo,
  icones, themes, chemins) ne vit que dans le fichier de configuration; rien de propre au groupe n'est dans le depot.
- Detail des modifications:
  - nginx-link-page.sh (1.1.20261111.093000): configuration en trois blocs: SITE_* (contenu partage), LINK_n_* (liens
    partages, numerotes sans trou) et PAGE_n_* (ENABLED, ENGINE, PATH, DIR, THEME, TITLE; une page par bloc).
  - Validation: chemins de page uniques, dossiers uniques et non imbriques, moteur "littlelink" seulement; "linkstack"
    est refuse avec un message clair (moteur reserve: application PHP/Laravel avec base de donnees).
  - --check affiche chaque page (chemin, dossier, moteur, actif ou non).
  - --update: LittleLink telecharge une seule fois (tag et commit epingles); un index.html par page active; un seul
    fragment nginx liens-publics.conf avec une location ^~ par page active; nginx -t avant rechargement, ancien fragment
    restaure en cas de refus.
  - --help: options en anglais, triees par ordre alphabetique, affichees en couleur sur un terminal.
  - nginx-link-page.conf.example: modele reecrit (SITE_*, LINK_n_*, PAGE_1_* actif, PAGE_2_* desactive, theme sombre).
  - nginx-tools-tests/test_nginx_link_page.py: tests reecrits pour le format multi-pages.
- Bugs corriges: aucun bogue de la version 1.0 n'est repris; la version 1.0 n'a jamais ete publiee. Lors de la reecriture,
  une boucle morte (references d'icones sans effet) a ete supprimee, et un tableau associatif indexe par une chaine vide
  est evite (erreur bash "bad array subscript" sinon).
- Garde-fous et cas limites: la verification des dossiers imbriques evite qu'une page masque une autre (/var/www/liens
  et /var/www/liens/deux); /liens/ ne couvre pas /liens2/ (le slash final est obligatoire); les numeros de pages et de
  liens doivent se suivre; les images (logo, icones) sont verifiees par leur contenu (PNG, JPEG, WebP, SVG) et limitees
  en taille; une icone builtin inconnue est refusee.
- Verifications effectuees: tests unitaires de nginx-tools-tests/test_nginx_link_page.py (configuration, installation
  avec faux git/curl/nginx/systemctl, commit inattendu, restauration sur echec de nginx -t, absence de donnees de groupe
  dans le depot), lances par le testeur; syntaxe bash -n; --version et --help verifies a la main.
- Action requise: aucune dans le depot. Sur le serveur: copier nginx-link-page.conf.example vers
  /etc/default/nginx-link-page.conf, le remplir (SITE_*, LINK_n_*, PAGE_n_*), puis lancer
  sudo nginx-link-page.sh --check, puis sudo nginx-link-page.sh --update. Lancer nginx-hardening.sh --update une fois
  pour creer le fragment vide inclus par _odoo-common.conf.


### 1.0.20261111.090000 - Link page built from a configuration file: no group data in the repository

- Title: nginx-link-page.sh builds and installs a LittleLink page under /liens/ from /etc/default/nginx-link-page.conf.
- Reason: the links, the logo and the icons of a group must not be published on GitHub; everything specific to a group is read from the configuration file.
- Changes: new program nginx-link-page.sh (options --changelog, --check, -c/--config, -h/--help, --lang, --update, --version, --yes); configuration read with KEY=VALUE keys (PAGE_*, LINK_n_LABEL, LINK_n_URL, LINK_n_ICON, LINK_n_ICON_DARK), links numbered without gaps; nginx-link-page.conf.example (placeholders only); LittleLink v3.11.0 fetched at the pinned tag and commit; logo and icons downloaded over HTTPS (max 512 KB), kept only if PNG, JPEG, WebP or SVG; index.html generated with HTML escaping; snippet liens-publics.conf (location ^~ with alias, GET and HEAD only, Content-Security-Policy, nosniff, Referrer-Policy); nginx -t before reload, previous snippet restored on refusal. Tests: test_nginx_link_page (13 tests, including a check that the repository holds none of the group's data).
- Bugs fixed: symptom: a label containing < was shown as "<lt;" (found while testing); diagnosis: bash 5.2 reads an unescaped & in a replacement as the matched text; fix: the replacements escape the & (\&amp;).
- Safeguards and edge cases: a commit other than the pinned one is refused before any copy; a URL that is not https is refused at --check; a missing icon or an image of another type stops the installation before any file changes; the page is served with GET and HEAD only; PAGE_ENABLED=no keeps the files and removes the location; --update asks for confirmation (--yes without a terminal); --update requires root.
- Checks performed: test_nginx_link_page (13 tests); bash -n nginx-link-page.sh; --check on nginx-link-page.conf.example.
- Action required: copy nginx-link-page.conf.example to /etc/default/nginx-link-page.conf, fill in the group's values, then run sudo nginx-link-page.sh --update. Note: HSTS (hsts.conf) is a server-level header; the /liens/ location declares its own headers, so HSTS is not repeated there.

## nginx-log-audit.sh

### 2.93.20261110.213818 - A lone burst and robots.txt are no longer reasons to propose a ban

- Title: --investigate no longer treats a single burst of pages, nor a 404 on /robots.txt, as a sign of hostility.
- Reason: request of the administrator on 2026-11-10. The address 34.16.118.141 (Google Cloud, score 4/7, 365-day ban proposed) had not been banned; the administrator asked that this kind of case no longer be recommended for a ban.
- Changes: nginx-log-audit.sh: a burst of pages (PAGE_BURST) adds 1 to the score but no longer to the hostility count; when a burst is the only sign, the reason "une seule rafale de pages, sans signe fort : un robot qui lit vite, pas une attaque" is given. The summary line now reads "Signes d'hostilité : N (...) ; d'automatisation : M (...)". New function sans_robots_txt(): GET and HEAD requests for /robots.txt are removed from the refused requests (urls_refusees, the "refus=" evidence line and the INV_REFUS count). nginx/snippets/securite-commune.conf: rule 5 no longer matches robots\.txt; nginx/VERSION 1.27.20261110.213818. Tests: test_nginx_log_audit (two new cases), test_nginx_uri (class RobotsTxtNonRefuse). The fixture of the interactive ban question now adds three requests to /.env, so the question is still asked when hostility is real.
- Bugs fixed: symptom: a robot reading quickly, with a 404 on /robots.txt, was proposed for a 365-day ban (score 4/7, verdict BANNIR). Diagnosis: (1) the burst rule also added to the hostility count, so one burst counted as an attack sign; (2) rule 5 of securite-commune.conf matched /robots.txt, so the 404 was logged as a refused probe in blocked-probes.log and counted as a sensitive-file probe. Fix: a burst is an automation sign only, and robots.txt is excluded from the refusal rule and from the counts. Not addressed in this version: the synthesis line can still say "à examiner" where the detailed analysis says BANNIR in other cases.
- Safeguards and edge cases: a burst together with a sweep (balayage), three or more sensitive-file requests, mass errors, a fake search engine or the catch-all sensor still produces hostility and the usual proposal. Any ban still goes through the score (threshold 3), the white list and the administrator's own confirmation. The fail2ban filter nginx-blocked-probes.filter.conf and the heredoc of nginx-hardening.sh are unchanged, as the tests require them to stay identical.
- Checks performed: test_nginx_log_audit: test_une_seule_rafale_ne_fait_pas_recommander_le_bannissement, test_robots_txt_refuse_n_est_pas_compte_comme_une_attaque; test_nginx_uri: RobotsTxtNonRefuse; the three terminal-input tests of ChkNginxLogs (question answered by Ctrl-C, erase key, slow answer).
- Action required: run `sudo nginx-hardening.sh --update` to deploy the new rule 5 on the server. Then `sudo nginx-log-audit.sh prod --investigate 34.16.118.141` should no longer recommend a ban.

### 2.92.20261109.190000 - Erase key (^H) in the questions

- Title: the questions read without readline now use it.
- Reason: report of the administrator on 2026-11-09.
- Changes: demander_oui() (outside the subshell path) and demander_oui_strict(): "tty_ligne; read -e -r -p".
- Bugs fixed: symptom: in a question, the erase key showed "3^H^H" and the answer kept the ^H characters; diagnosis: the kernel line mode (stty icanon echoe, put back by tty_ligne) knows ONE erase key only (stty erase, usually ^?), while some terminals (PuTTY, some ssh clients) send ^H; ECHOE does not help when the key is not the erase key; fix: the answers are edited by readline (read -e) or by our own line editor, where ^H AND ^? erase.
- Safeguards and edge cases: answers by a pipe unchanged.
- Checks performed: test_saisie_terminal, test_nginx_log_audit (^H and ^?) [OK]; ShellCheck: no new note.
- Action required: none.

### 2.91.20261103.133244 - Systematic sweep and incomplete User-Agent signs; exact-IP Odoo logins; short account list

- Title: --investigate detects systematic sweeps and incomplete browser User-Agents, never proposes to lift them, and answers "which account logged in from this address" directly.
- Reason: --unban-low-score proposed to lift 125.59.124.161, which had read 440 distinct URLs (every combination of the event tag filters, under several language prefixes) with a User-Agent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" (no "KHTML, like Gecko", which a real browser always sends), and had been detected 13 times by fail2ban over 8 days. The verdict said "a robot that reads fast". The list of 50+ Odoo accounts (time coincidence over 2 hours) was long and useless, and the user wanted to know which logged-in account had used this address.
- Changes: nginx-log-audit.sh: investigate_and_propose has two new clues, "Balayage systematique" (at least 30 query variants of one page, or 100 distinct URLs repeated under 2 or more language prefixes) and "User-Agent de navigateur incomplet" (AppleWebKit without KHTML, 20 requests or more); each adds 1 to the score and to the hostility signs. recommander: with a sweep the verdict is never "lever" (GARDER LE BANNISSEMENT with a firewall ban, LAISSER A FAIL2BAN with a temporary fail2ban ban, A EXAMINER when not banned) and the text "a robot that reads fast" is not given. New line "Aucun compte Odoo ne s'est connecte DEPUIS cette adresse (journal d'Odoo, 100 jours, N connexions lues)" (or the list of accounts that did, as before). comptes_bd_ip: more than 5 accounts in the 2 hour margin are only counted, not listed. lang/nginx-log-audit.en.po: 17 entries. Files: nginx-log-audit.sh, lang/nginx-log-audit.en.po, doc/fr and doc/en 02-nginx-log-audit.md, tests.
- Bugs fixed: symptom: a scraper proposed for a lift. Diagnosis: the engine only counted bursts, sensitive files, errors and fake engines; enumeration of filters and a truncated User-Agent were not signs. Fix: the two clues above and the rule in recommander.
- Safeguards and edge cases: verified search engines, protected addresses and addresses with an Odoo login keep their earlier verdicts (those branches come first); the language-prefix test only counts a prefix whose pages also exist without prefix (at least 5 shared pages), so "/js/..." style paths are not taken for languages; a score of 3 with a sign still proposes a ban only with the usual question (never automatic).
- Checks: new test_291 (sweep fixture gets both clues and no lift; a visitor with 3 pages gets neither); test_unban_low_score_*; i18n catalogue; test_ban_gate version string.
- Action required: none. Run `sudo nginx-log-audit.sh prod --unban-low-score` again: 125.59.124.161 should no longer be proposed for a lift.

### 2.90.20261103.131310 - --unban-low-score: suspicious URLs behind each ban

- Title: --unban-low-score lists the suspicious URLs that may have caused the ban, above each question.
- Reason: to confirm the verdict by eye before lifting or banning, the user wanted some of the suspicious URLs that got the address banned in the first place.
- Changes: nginx-log-audit.sh: new function urls_suspectes_ip (pages refused by nginx from blocked-probes.log through urls_refusees, sensitive pages of the site log from the shared copy, pages asked at the catch-all sensor; at most 8 lines, "Nx page (code)", most frequent first). The list is collected while the shared log copy exists (URLS_OF) and printed after the full --investigate result, before the lift question and before the ban question. lang/nginx-log-audit.en.po: 2 entries. Files: nginx-log-audit.sh, lang/nginx-log-audit.en.po, doc/fr and doc/en 02-nginx-log-audit.md, tests.
- Bugs fixed: none.
- Safeguards and edge cases: only the addresses that get a question are listed (no extra cost for the others); with no suspicious URL the line says so, which is what a lift should look like; the sensitive pages use the same SENSITIVE_RE as the scan (Odoo or WordPress aware); read-only.
- Checks: question test checks the "no suspicious URL" case; structure test for the two displays and the three sources; test_unban_low_score_*, test_ban_gate; i18n catalogue of this program.
- Action required: none.

### 2.89.20261103.130619 - --unban-low-score: exit code fixed, full --investigate result before each question

- Title: --unban-low-score no longer ends with an "unexpected stop" error, and shows the whole result of --investigate above each question.
- Reason: (1) with 2.88 the command ended with "ARRET INATTENDU DU SCRIPT (code 123) ... Commande fautive : exit 0" when no address had to be lifted. (2) Before lifting or banning, the user wanted more information, namely the result of --investigate.
- Changes: nginx-log-audit.sh: lot_arreter (EXIT trap that stops running investigations and removes the shared folder, always returns 0 and keeps the exit code); lire_enquete keeps the whole output of the investigation (ENQUETE_SORTIE); in --unban-low-score the block "Resultat complet de nginx-log-audit.sh --investigate IP" is printed right above each lift question and each ban question. lang/nginx-log-audit.en.po: 4 entries. Files: nginx-log-audit.sh, lang/nginx-log-audit.en.po, doc/fr and doc/en 02-nginx-log-audit.md, tests.
- Bugs fixed: symptom: code 123 and the ERR message on a normal "exit 0". Diagnosis: the 2.88 EXIT trap ran "jobs -p | xargs -r kill"; kill failed on a finished process, xargs returned 123 and the failing trap replaced the exit code and fired the ERR trap. Fix: a loop with "kill ... || true" and "exit $ec" in the trap.
- Safeguards and edge cases: the full result is shown for the addresses that get a question (lift or ban) even with --yes, for the record; protected addresses are still skipped; the summary list before the questions is kept.
- Checks: new test: no address to lift gives code 0 and no "ARRET INATTENDU"; the question test checks the full result header; test_unban_low_score_* and test_ban_gate; i18n catalogue of this program.
- Action required: none.

### 2.88.20261103.121008 - --unban-low-score: logs read once, investigations in parallel

- Title: --unban-low-score reads the logs and the Odoo journal once for all banned addresses and runs the investigations in parallel.
- Reason: with 128 banned addresses the command took about 20 s per address (more than 40 minutes). Each address started a full --investigate that decompressed all the site, catch-all and fail2ban logs again, read the Odoo journal for 100 days again (journalctl, up to 60 s) and waited for the network one step at a time. The user asked why it was so long and why Odoo was queried every time.
- Changes: nginx-log-audit.sh: lire_enquete (reads the output and the RÉSUMÉ line of one run; verdict_par_enquete now uses it), lot_preparer (one read of fail2ban.log, catch-all logs, blocked-probes.log, site log and Odoo logins, pre-filtered on the banned addresses, shared through NGINX_TOOLS_BATCH_CACHE), lot_chrono, enqueter_lot (parallel runs, NGINX_TOOLS_JOBS, 4 at most by default, nproc otherwise), lot_nettoyer. lire_chrono, charger_logins and the --investigate block use the shared copies when the variable is set. lang/nginx-log-audit.en.po: 4 entries. Files: nginx-log-audit.sh, lang/nginx-log-audit.en.po, doc/fr and doc/en 02-nginx-log-audit.md, tests.
- Bugs fixed: none in the verdicts. Performance symptom: the Odoo journal and the logs were read again for each address. Diagnosis: every --investigate is a separate process with no shared data. Fix: shared pre-filtered copies and parallel runs.
- Safeguards and edge cases: each investigation still runs the same code on the lines of its own address (exact filter on the first field), so the verdict is unchanged; the catch-all copy stays non-empty when the sensor log is non-empty (the code tells "no sensor log" from "no request"); if the temporary folder cannot be created the old sequential path is used; the temporary folder is removed on exit and the children are stopped on interruption; the shared copy is removed before any ban or lift so --ban and --unban read fresh data. The Odoo database is queried only for addresses that asked for a page needing a session (rule of 2.72, unchanged).
- Checks: bash -n; test_unban_low_score (verdicts unchanged); new test: journalctl called once for 3 addresses; test_i18n for this program; test_ban_gate version string.
- Action required: none. Optional: NGINX_TOOLS_JOBS=N to set the number of parallel investigations.

### 2.87.20261103.114021 - --unban-low-score: ban offer for BANNIR verdicts and strict o/n questions

- Title: --unban-low-score now offers a durable ban when --investigate says BANNIR, and its questions require an explicit o or n.
- Reason: on dev, 185.218.86.26 had the verdict BANNIR (3/7, banned only temporarily by the fail2ban jail nginx-blocked-probes) and the user was never asked to ban it. The lift question "Debannir ... [o/N]" also accepted any key as "no" (and Enter), so an answer was easy to lose.
- Changes: nginx-log-audit.sh: new function demander_oui_strict (no default; asks again until o/oui/y/yes or n/non/no; Ctrl-C or end of input counts as no). In the --unban-low-score block: addresses with the verdict BANNIR are collected in BAN_IPS; the "no lift recommended" case no longer exits early so the ban offer is always reached; for each BANNIR address the investigation block is shown and the question "Bannir durablement IP ... [o/n]" runs `--ban IP --yes --reason ...` (which keeps its own score gate); the lift question uses demander_oui_strict and prints a line for a "no" answer. lang/nginx-log-audit.en.po: 9 new entries. Files: nginx-log-audit.sh, lang/nginx-log-audit.en.po, doc/fr and doc/en 02-nginx-log-audit.md, tests.
- Bugs fixed: symptom: a BANNIR address stayed only under its temporary fail2ban ban with no question. Diagnosis: the block only handled LEVER LE BANNISSEMENT and left early when nothing had to be lifted. Fix: ban offer step added after the lift step.
- Safeguards and edge cases: a ban is never automatic: with --yes, --no-prompt or no terminal the program only prints the command `nginx-log-audit.sh --ban IP`. Protected IPs (white list, team, server) are never offered. The ban itself still goes through the --ban gate (score and CDN checks) and its journal.
- Checks: bash -n; test_i18n (nginx-log-audit catalogue complete); new tests test_unban_low_score_question_stricte_o_ou_n (pseudo-terminal: invalid answer asked again, then o lifts and prints the result) and test_unban_low_score_propose_le_bannissement_des_ip_a_bannir; test_ban_gate version string updated.
- Action required: none. Run `sudo nginx-log-audit.sh dev --unban-low-score` and answer o or n for 185.218.86.26.

### 2.86.20261103.112227 - --theme N: color themes

- Title: --theme N: color themes.
- Reason: request of the administrator on 2026-11-03: a --theme N option for all the programs (dark background, light background, etc.), making sure that every color reads on the chosen background. Delivered first for app-log-live.py, web-monitor.py and nginx-log-audit.sh; the other programs follow on request.
- Changes:
  - New option --theme N (0 to 4) and key THEME of the configuration (config_defaut); new function theme_sgr; C_RED, C_YELLOW, C_GREEN, C_BOLD, C_MAL and the colors of --changelog come from the theme.
  - The theme is validated (error message and exit code 1 for a value other than 0 to 4) and exported as NGINX_TOOLS_THEME for the programs launched.
  - lang/nginx-log-audit.en.po, doc/fr and doc/en (02-nginx-log-audit.md, nginx-log-audit.conf.example).
- Bugs fixed: none.
- Safeguards and edge cases: theme 0 changes nothing; without python3 or without apps/_theme.py the original codes are kept; colors stay limited to a terminal.
- Checks performed: test_theme.py (invalid theme, --changelog on a terminal with each theme, configuration and environment), test_i18n for nginx-log-audit.
- Action required from the user: none. To use a theme everywhere: THEME=2 in /etc/default/app-default.conf (or ~/.app-default.conf), or --theme N on one run; python3 apps/_theme.py --demo shows the themes.

### 2.85.20261103.103805 - One verdict for bans: --unban-low-score and --unban-check call --investigate

- Title: the recommendations to ban or lift come from a single engine, the one of --investigate.
- Reason: request of the administrator on 2026-11-03: --unban-low-score showed 185.218.86.26 as 0/7 "LEVÉE recommandée" while --investigate gave 3/7 "BANNIR"; the recommendations differed from one option to the other. --unban-low-score must call --investigate, and the programs must be checked and made uniform.
- Audit of the programs: app-log-live.py (ban proposals) and web-monitor.py (repeat offenders) already ask `nginx-log-audit.sh --investigate --no-prompt` and follow its verdict: nothing to change. The only second logic was inside nginx-log-audit.sh (decide_unban, used by --unban-check and --unban-low-score, with a score computed without the RDAP owner of the block, without blocked-probes.log and without the same catch-all counts).
- Changes:
  - New verdict_par_enquete IP: runs `--investigate IP --no-prompt` (sub-process, French) and reads its RÉSUMÉ line (verdict, reason, score). UNBAN_VERDICT: lever (LEVER LE BANNISSEMENT), garder (BANNIR, GARDER LE BANNISSEMENT, LAISSER À FAIL2BAN, LAISSER À CROWDSEC), verifier (other verdicts), incoherente, trace (no verdict).
  - --unban-low-score rewritten on verdict_par_enquete: one step "Enquête i/N" per address; the table shows the score and the verdict of --investigate (no more "?/7"); the blocks of the addresses to lift are shown; the lift needs the verdict LEVER LE BANNISSEMENT (checked again before each lift, even with --yes).
  - --unban-check: evaluer_bannissement shows the block of --investigate then the conclusion and the offer to lift (new proposer_levee); the logs are no longer prepared in this process.
  - recommander(): SQL injection rule (2.68) moved here: a verdict LEVER LE BANNISSEMENT becomes GARDER LE BANNISSEMENT when the logs hold an injection (protected addresses excepted), so --investigate says the same.
  - RÉSUMÉ line: score added as 6th field (app-log-live.py reads the first fields only).
  - Removed: decide_unban, preparer_journaux_unban, the unban-check branch of investigate_and_propose, INV_MODE, DERNIER_SCORE, MODE_EVALUATION.
  - lang/nginx-log-audit.en.po, doc/fr and doc/en 02-nginx-log-audit.md; tests: class ChkNginxLogs285 (3 tests), unban tests adapted, test_sqli_unban follows recommander, test_ban_gate version.
- Bugs fixed:
  - Symptom: 185.218.86.26 listed 0/7 and "LEVÉE recommandée" by --unban-low-score, 3/7 "BANNIR" by --investigate. Diagnosis: two separate logics (the in-process one ignored the RDAP hosting owner and the refusals of blocked-probes.log). Fix: one engine.
- Safeguards and edge cases: an address is never lifted unless --investigate says LEVER LE BANNISSEMENT; protected addresses are never lifted by --unban-low-score; the SQL injection rule keeps the ban; without verdict the address is "trace" (manual decision). Cost: one --investigate per banned address (about 5 s each, 29 addresses: 2 to 3 minutes), shown by one progress line per address.
- Checks performed: ChkNginxLogs285, all the --unban tests of test_nginx_log_audit, test_sqli_unban, test_ban_gate, test_i18n catalogue of nginx-log-audit.
- Action required from the user: none.

### 2.84.20261103.081135 - The analysis reports requests to the password reset and sign-up forms

- Title: --investigate notes 10 or more requests to /web/reset_password or /web/signup, as information.
- Reason: request of the administrator on 2026-11-03: "why was 206.42.109.58 not seen as malicious? It made many attempts to change a password." The investigation showed SofyaBot (811 GET requests, one burst, no sensitive file): a crawler that follows the links of the login pages, score 1/7.
- Changes:
  - recommander(): note "formulaires de compte : N requêtes à /web/reset_password ou /web/signup" when N >= 10, with the explanation and the advice to check Odoo's failed logins if the address is not a known robot. No hostility point is added.
  - lang/nginx-log-audit.en.po: the new messages. doc/fr and doc/en 02-nginx-log-audit.md. nginx-tools-tests/test_nginx_log_audit.py: test_284_formulaires_de_compte_signales_sans_score.
- Bugs fixed: none (the verdict REFUSER LE ROBOT PAR SON NOM for a named crawler was right).
- Safeguards and edge cases: the access logs do not tell a form shown (GET) from a form sent (POST) in the URL list, so a score would ban crawlers that only read the links; below 10 requests there is no note.
- Checks performed: test_nginx_log_audit and test_ban_gate (87 tests).
- Action required from the user: none.

### 2.83.20261103.071054 - awk warnings in the recommendation fixed (static files regex)

- Title: the analysis block of --investigate no longer prints "awk: warning: escape sequence" and the static-file filter of the request nature works as written.
- Reason: request of the administrator on 2026-11-03: "there is an AWK error" (two warnings "escape sequence `\.' / `\?' treated as plain" before ANALYSE ET RECOMMANDATION).
- Changes: nature_requetes() passes STATIC_RE to awk through ENVIRON instead of -v. nginx-tools-tests/test_nginx_log_audit.py: new test_283_aucun_avertissement_awk_et_nature_des_requetes.
- Bugs fixed:
  - Symptom: two awk warnings in every --investigate output. Diagnosis: awk -v interprets backslash sequences, so \. and \? of STATIC_RE (written for the regex) were changed to . and ?, and the pattern was altered. Fix: ENVIRON, which does not interpret the value (the same method already used at the other STATIC_RE use of the program).
  - Side effect fixed: with the altered pattern, static files (.js, .png...) were not always set aside, so the nature of the requests (e.g. RSS discovery) could be missed.
- Safeguards and edge cases: other awk -v regex variables (SQLI_RE) contain no backslash and are unchanged.
- Checks performed: the new test fails with -v (nature missed) and passes with ENVIRON; test_nginx_log_audit and test_ban_gate run.
- Action required from the user: none.

### 2.82.20261103.065758 - CrowdSec alone is no reason to recommend a lift

- Title: an address blocked only by the CrowdSec community list gets the verdict LAISSER À CROWDSEC and no lift command; a lift recommended for a manual ban or fail2ban jail warns that --unban also removes the CrowdSec list.
- Reason: request of the administrator on 2026-11-03: "why suggest unbanning 51.75.119.168 if it is blocked by the CrowdSec community list (crowdsec-blocklist-v4)?"
- Changes:
  - recommander(): banni_local (firewall rule or fail2ban jail) is separated from the CrowdSec state; new case cs_seul (only CrowdSec blocks) with the verdict LAISSER À CROWDSEC, the reason "the list comes from other servers" and the note on the permanent exception in the allow file; when a local ban and CrowdSec both exist, the LEVER verdict adds a warning that --unban also lifts CrowdSec. A robot that names itself is lifted only if a local ban exists.
  - lang/nginx-log-audit.en.po: the new messages. doc/fr and doc/en 02-nginx-log-audit.md. nginx-tools-tests/test_nginx_log_audit.py: new class ChkNginxLogs282 (2 tests).
- Bugs fixed:
  - Symptom: --investigate (and section 6 of --unban-check) recommended LEVER LE BANNISSEMENT, with the reason "fail2ban catches a new burst by itself", for an address blocked by CrowdSec. Diagnosis: recommander() counted the CrowdSec list as a ban and, with no local trace, concluded that nothing justified it any more; the command --unban also adds a permanent exception to the CrowdSec allow file. Fix: see Changes.
- Safeguards and edge cases: protected addresses, search engines, logged-in members and CDN addresses are still lifted when CrowdSec alone blocks them (the program's own rules decide there); no automatic action changes, only the advice; app-log-live.py is not affected (it proposes bans only when the verdict is BANNIR).
- Checks performed: test_nginx_log_audit and test_ban_gate (85 tests OK); test_i18n: only the failures already present on main.
- Action required from the user: none.

### 2.81.20261102.235220 - --unban-low-score investigates each address before lifting its ban

- Title: before asking to lift a ban, --unban-low-score runs nginx-log-audit.sh --investigate for each address whose lift --unban-check recommends, shows the verdict and the reasons, and lifts only if the investigation agrees.
- Reason: request of the administrator on 2026-11-02: "before unbanning, can you investigate the IPs that --unban-low-score wants to unban?"
- Changes:
  - enquetes_compactes moved before the --unban-low-score block (it was defined after it, so it could not be called there). It now stores the verdict of each address in ENQUETE_VERDICT_OF, takes its title from ENQUETES_TITRE and can hide the final commands (ENQUETES_SANS_COMMANDES=1).
  - --unban-low-score: after the table, a block "Enquêtes avant la levée" (the same compact view as section 6 of --unban-check); the question now reads "Débannir IP (score N/7, enquête : lever, banni par SOURCE) ?".
  - lang/nginx-log-audit.en.po: the new messages. doc/fr and doc/en 02-nginx-log-audit.md. nginx-tools-tests/test_nginx_log_audit.py: the existing --unban-low-score test checks the investigation, and a new test checks that the lift depends on the verdict.
- Bugs fixed: none.
- Safeguards and edge cases: an address is lifted only if the investigation says "LEVER LE BANNISSEMENT"; any other verdict (BANNIR, GARDER LE BANNISSEMENT, LAISSER À FAIL2BAN...) or no verdict leaves the ban in place, even with --yes, and the program names the verdict and the --investigate command. All the addresses to lift are investigated (no limit of UNBAN_CHECK_INVESTIGATIONS here, since each one is about to be lifted). Protected addresses are still never lifted. The investigations are read-only.
- Checks performed: test_nginx_log_audit and test_ban_gate (82 tests OK); test_i18n: only the failures already present on main (nginx-hardening, apps/_listes.sh).
- Action required from the user: none.

### 2.80.20261102.233751 - --unban-check runs the investigations of the bans to check (section 6)

- Title: at the end of its report, --unban-check runs nginx-log-audit.sh --investigate for each ban of section 5 and shows its verdict, its reasons and the command to run, then a summary table and the --ban / --unban commands.
- Reason: request of the administrator on 2026-11-02: "--unban-check should start the investigations at the end of its report" instead of listing the commands to run by hand for each address (18.226.62.38, 34.179.188.26, 35.246.245.129, 51.75.119.168, 82.166.33.79).
- Changes:
  - New function enquetes_compactes IP...: runs --investigate for each address (this program, --no-prompt, NGINX_TOOLS_LANG=fr so the block is found by its French title, then translated with the rest of the output; INV_RESUME_FILE for the summary), shows only the block ANALYSE ET RECOMMANDATION, then "Synthèse" (IP, verdict, main reason) and the commands. At most UNBAN_CHECK_INVESTIGATIONS addresses (environment variable, 20 by default).
  - revue_controles(): new section 6 after section 5 (which keeps its commands, for the full report); "copiez les sections 1 à 6".
  - recommander(): an address with no trace left in the logs kept (site, nginx refusals, catch-all sensor) says so, instead of "aucun signe d'hostilité".
  - lang/nginx-log-audit.en.po: the new messages, and "  Commande : " and "Raison principale", which stayed in French in English output (sections 1 to 4 of the review and the advice).
  - doc/fr and doc/en 02-nginx-log-audit.md: section 6.
  - nginx-tools-tests/test_nginx_log_audit.py: test_unban_check_une_seule_rafale_a_verifier checks section 6 (verdict, summary, command); test_ban_gate.py: version.
- Bugs fixed:
  - Symptom: in English, "Commande :" and "Raison principale" stayed in French. Diagnosis: no catalogue entry (the extraction of the test does not see them as French). Fix: entries added.
- Safeguards and edge cases: read-only (the investigations ban nothing; the commands check again and ask); an investigation without a verdict says so with its command; more than 20 addresses: the first 20, the others with the commands of section 5. Each investigation takes a few seconds: with 5 addresses the report is about a minute longer (cron included).
- Checks performed: bash -n; test_nginx_log_audit and test_ban_gate [OK]; test_i18n: catalogue of nginx-log-audit [OK]; section 6 previewed in French and in English.
- Action required: none.

### 2.79.20261102.230844 - The investigation counts the requests refused by nginx (blocked-probes.log)

- Title: --investigate (and the investigation run by --ban) adds the requests of the address found in blocked-probes.log to those of the site log, so that the refused probes count in the score like the others; its summary line gives the number of fail2ban bans too.
- Reason: request of the administrator on 2026-11-02: app-log-live.py proposed to ban 132.196.59.85 and 45.138.12.41, then nginx-log-audit.sh --ban refused them. For 132.196.59.85, the evidence said "justifié" (28 requests refused by nginx: .php files, wp-content/plugins/.../wp_filemanager.php) but the investigation, which read only the site log (2 requests), gave 1/7.
- Changes:
  - --investigate block: after merging the site log, the lines of the address in /var/log/nginx/blocked-probes.log* (same combined_host format) are added to the merged file (INV_REFUS); the header says "N requêtes dans tout l'historique disponible, dont M refusées par nginx (blocked-probes.log)".
  - recommander(): the line "RÉSUMÉ|ip|verdict|reason" gets a fifth field, the number of fail2ban bans (read by app-log-live.py 1.155); the summary of several addresses reads it with one more field.
  - vpn_lire(): passes the abuse mailbox of the block to apps/_vpn.py 1.1 (132.196.59.85: abuse@microsoft.com -> "hébergeur (Microsoft)", consistent with the rented-server clue).
  - lang/nginx-log-audit.en.po: the new fragments.
  - nginx-tools-tests/test_nginx_log_audit.py: new class ChkNginxLogs279 (the case of 132.196.59.85: score 3/7, BANNIR, summary line with 5 fields); test_ban_gate.py: version.
- Bugs fixed:
  - Symptom: "LES PREUVES NE JUSTIFIENT PAS CE BANNISSEMENT (verdict des preuves : justifie ; l'enquête ne recommande pas le bannissement, score inférieur à 3/7)" for an address that sent 28 webshell probes. Diagnosis: the refusals of our nginx rules go to blocked-probes.log, which preuves_ip reads but the investigation did not; the score saw 2 requests. Fix: those lines are part of the investigation.
- Safeguards and edge cases: only the lines that start with the address are added; no blocked-probes.log: unchanged; the daily report (section [10]) is unchanged (fail2ban handles the refused probes there). The --ban gate keeps its rule (score 3/7), now computed on all the requests of the address.
- Checks performed: bash -n; test_nginx_log_audit and test_ban_gate [OK] (with ChkNginxLogs279); test_i18n: catalogue of nginx-log-audit [OK].
- Action required: none.

### 2.78.20261102.224544 - --investigate ends with a verdict and a recommendation; several addresses with a summary

- Title: --investigate re-reads its own findings and ends with "ANALYSE ET RECOMMANDATION": one verdict (NE PAS BANNIR, LEVER LE BANNISSEMENT, GARDER LE BANNISSEMENT, BANNIR, LAISSER À FAIL2BAN, REFUSER LE ROBOT PAR SON NOM, AUCUNE ACTION, À EXAMINER), its reasons, notes and the command to run. --investigate IP1 IP2 (or IP1,IP2) investigates each address and ends with a summary table and the commands.
- Reason: request of the administrator on 2026-11-02: "instead of sending you the investigation report every time, can nginx-log-audit.sh --investigate re-validate as you do and give me recommendations? There are several IPs a day to investigate."
- Changes:
  - New functions: recommander (decision tree below), robots_declares (names that robots give in their User-Agent: "Name/1.0" or "name (+https://...)", browser and system words and HTTP libraries left out), robot_refuse (name already in bot_blocker.conf: NGINX_TOOLS_BOT_BLOCKER, default /etc/nginx/conf.d/bot_blocker.conf, otherwise the copy of the repository), nature_requetes (job offers, RSS feeds or forms when one kind makes at least half of the pages).
  - Decision tree, in this order: protected address, verified search engine, Odoo account logged in, CDN node -> NE PAS BANNIR (LEVER LE BANNISSEMENT if banned; À EXAMINER for a CDN with a strong sign); strong sign or score at the threshold with hostility -> GARDER (manual ban in place), BANNIR (duration by origin given) or LAISSER À FAIL2BAN (score under the threshold); otherwise -> robot that names itself and is not refused yet: REFUSER LE ROBOT PAR SON NOM (or LEVER then add it to bot_blocker.conf, when banned); banned without hostility: LEVER (fail2ban catches a new burst); else AUCUNE ACTION. Notes: name already refused, nature of the requests, VPN / Tor / relay, access provider, fail2ban and CrowdSec bans in progress, state not readable without root.
  - investigate_and_propose(): keeps the facts (INV_*: score, signs, User-Agents, URLs, catch-all count, motifs) for the advice; with --investigate, the ban question comes after the advice, and only in a terminal, as root, without --no-prompt (otherwise the command is in the advice).
  - afficher_bannissements(): keeps the ban state (ETAT_PARE_FEU, ETAT_JAILS, ETAT_CROWDSEC, ETAT_F2B_BANS, ETAT_ECHEANCE).
  - Address with no request to the site: the advice still uses the bans, the catch-all sensor and the owner of the block.
  - Option parsing: --investigate takes several addresses (following arguments that look like addresses, or a comma list); each is validated; with more than one, each is run as a child (--no-prompt) and its verdict collected (INV_RESUME_FILE), then "SYNTHÈSE DES N ADRESSES ENQUÊTÉES" and the --ban / --unban commands to run.
  - Help, header comment, doc/fr and doc/en nginx-log-audit.conf.example; doc/fr and doc/en 02-nginx-log-audit.md: new section on the verdict; lang/nginx-log-audit.en.po: the new messages ("BANNIR" -> "BAN" for the verdict; the word to type for an exception stays BANNIR in its own sentences).
  - nginx-tools-tests/test_nginx_log_audit.py: new class ChkNginxLogs278 (7 tests: fake Googlebot + catch-all + hosting -> BANNIR with 365 days; robot naming itself, banned -> LEVER then bot_blocker.conf; name already refused and free name -> REFUSER LE ROBOT PAR SON NOM; verified engine -> NE PAS BANNIR; Tor exit; several addresses and summary; module apps/_vpn.py).
- Bugs fixed: none.
- Safeguards and edge cases: the advice never bans or lifts anything: it gives the command, and --ban / --unban still check again and ask. The line "Score N/7 : bannissement recommandé." stays (the --ban gate reads it). The country is not a criterion (it is the server's, not the person's). An inconsistent investigation (address changed) gets no advice. A CDN is never advised for a ban without a strong sign (CLAUDE.md rule).
- Checks performed: bash -n; test_nginx_log_audit and test_ban_gate: 86 tests [OK]; test_i18n: catalogue of nginx-log-audit [OK]; English output of the advice previewed.
- Action required: none.

### 2.77.20261102.224544 - Network name shown when the RDAP organisation says nothing ("Admin")

- Title: when the RDAP organisation of a block is generic ("Admin", "Abuse", "NOC", "-"...), the network name is shown instead, in the owner line, the rented-server clue and the origin of a ban.
- Reason: request of the administrator on 2026-11-02, after "Provenance : hébergeur : Admin" for 45.138.12.41 (network TC-DATACENTER-LIMITED).
- Changes: reseau_lire() sets RESEAU_LABEL (organisation, or network name when GENERIC_ORG_RE matches); infos_reseau() shows it and says "nom du réseau ; organisation RDAP « Admin », sans information"; the rented-server clue and provenance_ip() use it. Same rule in apps/_vpn.py (owner_label).
- Bugs fixed: symptom "Provenance : hébergeur : Admin"; diagnosis: the organisation field was shown as it is; fix above.
- Safeguards and edge cases: a real organisation name is never replaced; an empty organisation already showed the network name.
- Checks performed: test_278_faux_googlebot_catch_all_hebergeur_bannir [OK].
- Action required: none.

### 2.76.20261102.224544 - Tor exits recognized (official list of the Tor project, cached one day)

- Title: --investigate says when the address is a Tor exit, from the official list (https://check.torproject.org/torbulkexitlist), and the advice notes that the address is shared by many users.
- Reason: request of the administrator on 2026-11-02 ("can you know whether a VPN is used?"), improvement 2 proposed.
- Changes: apps/_vpn.py tor_exits(): list downloaded with curl (otherwise wget), cached in NGINX_TOOLS_TOR_CACHE, /var/cache/nginx-tools/tor-exits.txt (root) or ~/.cache/nginx-tools/tor-exits.txt, refreshed when older than one day; vpn_lire() reads it; the line "Type d'adresse" says "sortie Tor (liste officielle du projet Tor du DATE)".
- Bugs fixed: none.
- Safeguards and edge cases: a failed download keeps the previous list; a download of fewer than 10 addresses (an error page) never replaces the cache; without network and without cache, nothing is said about Tor. Information only, outside the score.
- Checks performed: test_278_sortie_tor_reconnue, test_278_vpn_module_partage (refresh, failure keeps the list) [OK].
- Action required: none (the server must reach check.torproject.org once a day).

### 2.75.20261102.224544 - Type of address in the investigation: VPN, relay or hosting provider (shared with web-monitor.py)

- Title: --investigate shows "Type d'adresse": VPN (NordVPN, Mullvad, Proton...), relay (iCloud Private Relay, Cloudflare WARP), hosting provider, or no sign of any, from the owner of the block.
- Reason: request of the administrator on 2026-11-02, improvement 1 proposed: web-monitor.py already classified the addresses of the accounts, nginx-log-audit.sh did not.
- Changes: new module apps/_vpn.py (the list VPN_OWNERS moved from web-monitor.py, kind_of, owner_label); new function vpn_lire (VPN_TYPE, VPN_NOM); investigate_and_propose() prints the line after the owner of the block.
- Bugs fixed: none.
- Safeguards and edge cases: a guess from the owner's name, said as such ("serveur loué, ou sortie d'un VPN ou d'un proxy (impossible de distinguer)"); information only, outside the score; module missing: no line about the type, no error.
- Checks performed: ChkNginxLogs278 [OK]; web-monitor tests [OK].
- Action required: none.

### 2.74.20261102.220025 - --unban lifts every ban of the address itself: firewall, fail2ban jails, CrowdSec list

- Title: --unban IP finds and lifts every ban of the address (manual firewall rule, each fail2ban jail that holds it, CrowdSec community list) instead of telling the administrator to run "fail2ban-client set <jail> unbanip IP".
- Reason: request of the administrator on 2026-11-02: "nginx-log-audit.sh --unban 170.231.237.214" answered "no manual rule found, nothing to lift" and gave a fail2ban command to run by hand; the program should find the right jail and lift it itself.
- Changes:
  - --unban block rewritten: it lists what bans the address (ufw / iptables / ip6tables rule, jails whose "Banned IP list" contains it, ipsets crowdsec-blocklist-v4 and -v6), shows the list, asks once (--yes: no question) and a justification, then lifts each one: rule removed, "fail2ban-client set JAIL unbanip IP" for each jail, "ipset del" for each set. One "leve" line in bans.tsv, its justification starting with the sources lifted ("levé : pare-feu, fail2ban nginx-badrequests - ..."). persist_firewall when a rule or an ipset entry was removed. Exit code 1 when a lift failed; a final line names what was lifted.
  - CrowdSec list: the address is first added to the exception file of sync-crowdsec-blocklist.sh (CROWDSEC_ALLOW_FILE, from SYNC_CROWDSEC_ALLOW_FILE, default /etc/default/sync-crowdsec-blocklist.allow), with the date and the justification as a comment, once; without it the next synchronisation would block the address again.
  - NGINX_LOG_AUDIT_UNBAN_SCOPE=manual: the manual rule only, as before. Set by --unban-check (re-evaluation of a manual ban) and --unban-expired (expiry of a manual ban), so that they never lift a fail2ban ban that a jail has just set.
  - ip6tables rules of an IPv6 address are found and removed too.
  - Help, header comment, doc/fr and doc/en nginx-log-audit.conf.example and 02-nginx-log-audit.md (new paragraph on --unban); lang/nginx-log-audit.en.po: the new messages.
  - nginx-tools-tests/test_nginx_log_audit.py: new class ChkNginxLogs274 (4 tests: jail found and lifted, firewall and CrowdSec with exception written once, manual scope, nothing to lift); test_ban_gate.py: version.
- Bugs fixed:
  - Symptom: "Aucune règle de bannissement manuel (ufw/iptables) trouvée pour 170.231.237.214 - rien à lever", then a command to run by hand. Diagnosis: --unban handled only the manual firewall rule. Fix: the jails and the CrowdSec sets are searched and lifted by the program.
- Safeguards and edge cases: the list of bans found is shown before the question; nothing is lifted on a negative answer. A jail can ban the address again if it does the same again (said before the question). The exception for the CrowdSec list is written only when the address was in that list, and not twice. --unban-low-score and --unban-cdn keep their own lifting of fail2ban bans; their call of --unban for a manual ban may now also lift the other bans of that address, which is what they ask for. fail2ban stopped or absent: only the other sources are searched.
- Checks performed: bash -n; ChkNginxLogs274 (4 tests) [OK]; test_i18n: catalogue of nginx-log-audit [OK] (failures for nginx-hardening and apps/_listes.sh already exist on main).
- Action required: none.

### 2.73.20261102.214543 - Firewall bans expire; duration by origin of the address (BAN_DAYS_HOSTING, BAN_DAYS_ISP, BAN_DAYS_OTHER)

- Title: a manual firewall ban gets an expiry date that depends on the origin of the address (hosting provider 365 days, access provider 90 days, unknown 365 days by default); --unban-expired lifts the expired bans, every day by cron.
- Reason: request of the administrator on 2026-11-02: "the ban should not be permanent, without expiry. An EC2 address changes tenant over time [...] a variable in the configuration should set the duration (12 months?) and it can differ depending on the origin of the IP." Seen on 18.226.62.38 (AWS EC2, manual ban of 2026-09-28 without expiry).
- Changes:
  - New configuration keys and options: BAN_DAYS_HOSTING (--ban-days-hosting, default 365), BAN_DAYS_ISP (--ban-days-isp, default 90), BAN_DAYS_OTHER (--ban-days-other, default 365); 0 = no expiry; integers from 0 to 36500. --ban-days N (with --ban only): duration of that ban, whatever the origin. New option --unban-expired. Help, usage header, menu (--menu) and doc/fr, doc/en nginx-log-audit.conf.example updated (keys and options in alphabetical order).
  - New functions: provenance_ip (PROV_TYPE "hebergeur", "acces" or "inconnue", and PROV_TEXTE: reverse DNS with CLOUD_PTR_RE, then owner of the block with reseau_hebergeur, then ISP_PTR_RE or the address written in the reverse name), duree_ban_jours, cle_duree, echeance_calcul, echeance_ban (ban date and expiry of the ban in place, from bans.tsv), texte_echeance, cron_echeances_installer (/etc/cron.d/nginx-log-audit-expiry, every day at 04:23: --unban-expired --yes --no-prompt, log /var/log/nginx-log-audit-expiry.log; NGINX_LOG_AUDIT_CRON_DIR for the tests).
  - New constant ISP_PTR_RE (reverse names of subscriber lines).
  - note_ban(): optional columns 6 (expiry "YYYY-MM-DD HH:MM" or "jamais") and 7 (origin) for the events "banni" and the new "echeance" (expiry fixed later for a ban without one). The first 5 columns are unchanged; web-monitor.py reads only "banni" and "leve" and is not affected.
  - --ban: shows the origin, the duration and the key that gives it, then "jusqu'au DATE" instead of "indéfiniment"; writes the expiry in the journal; installs the cron. An address already banned without expiry gets one from today (ajouter_justification).
  - --unban-expired block (before --unban-cdn): table IP, ban date, expiry, decision; expiry computed and written once for a ban recorded before 2.73; rules absent from the journal left in place; one question (preview only without terminal, none with --yes); lifts through --unban (journal, persistent rules); counts checked on the firewall rules.
  - afficher_bannissements() (--investigate, --unban-check): "bannissement manuel, échéance DATE" (or "sans expiration (durée 0)", or "échéance non fixée (--unban-expired la calcule)") instead of "sans expiration"; history shows the expiry and the event "échéance fixée". --ban-history shows the expiry.
  - lang/nginx-log-audit.en.po: the new messages, and the 36 messages that had no English entry yet (--ban-sqli, --unban-cdn, the ban gate), so the catalogue test of this program passes again. The grep pattern "Score [0-9]/7 : bannissement recommandé" and the menu line stay untranslated (msgstr empty), like the other menu lines.
  - doc/fr and doc/en nginx-log-audit.conf.example: also --unban-cdn, which was missing from the list of command-line options (test_toutes_les_options_sont_dans_le_modele failed on main).
  - doc/fr and doc/en 02-nginx-log-audit.md: new section "Durée des bannissements (échéance)" / "Duration of bans (expiry)".
  - nginx-tools-tests/test_nginx_log_audit.py: new class ChkNginxLogs273 (5 tests); test_ban_gate.py: version.
- Bugs fixed:
  - Symptom: manual bans kept forever (18.226.62.38, 82.166.33.79, 140.82.7.85, 192.54.244.135, 192.54.244.141 since September and October 2026). Diagnosis: --ban added "iptables -I INPUT -s IP -j DROP" with no expiry, by design. Fix: expiry by origin, lifted by --unban-expired.
  - Found by the new tests: GNU date reads "2026-11-02 21:38 + 365 days" as a time zone offset (result: the next day). echeance_calcul writes "DATE N days" without a sign, which keeps the local time across daylight saving time.
- Safeguards and edge cases: no ban is lifted without its expiry date passed; a ban without a journal line is never lifted automatically; with the default durations, the bans of September and October 2026 expire from December 2026 (access provider) or September 2027 (others). 0 keeps the previous behaviour for that origin. A CDN address is never banned without an attack signature (unchanged rule); its origin is not used to shorten anything. Without network (no DNS, no RDAP) the origin is "inconnue" (BAN_DAYS_OTHER). The cron is not written when every duration is 0, or without root. Each lift goes through --unban, so it is journalised with the reason "échéance atteinte (bannie le ..., échéance ...)" and the persistent rules are saved again. The lock of modifying runs applies to --unban-expired (the nested --unban reuses it).
- Checks performed: bash -n; test_nginx_log_audit and test_ban_gate: 73 tests [OK] (with ChkNginxLogs272 and ChkNginxLogs273); test_i18n: catalogue of nginx-log-audit [OK] (the failures for nginx-hardening and apps/_listes.sh already exist on main); test_config_defaut, test_cles_modeles, test_conventions: same failures as main, minus test_toutes_les_options_sont_dans_le_modele for nginx-log-audit.sh, now [OK].
- Action required: after the merge, run nginx-log-audit.sh --unban-expired once in a terminal (as root): it shows the expiry of each current ban, writes it in the journal and installs the daily cron. Change BAN_DAYS_HOSTING, BAN_DAYS_ISP or BAN_DAYS_OTHER in /etc/default/nginx-log-audit.conf if the defaults do not suit.

### 2.72.20261102.213548 - Investigation: rented server recognized by the block owner (RDAP); Odoo accounts searched only after a session page

- Title: --investigate checks the clue "rented server" when the owner of the address block (RDAP) is a hosting provider, even if the reverse DNS does not show it; the list of Odoo accounts active during the requests is searched only when the address asked for a page that needs a session.
- Reason: request of the administrator on 2026-11-02, after the investigations of 140.82.7.85, 192.54.244.135 and 192.54.244.141 (job offer robots). 140.82.7.85 belongs to "Vultr Holdings, LLC" (RDAP) but its reverse DNS is valtrona.eu: the clue was not checked. The three reports listed 1, 12 and 2 members of the site as "accounts active during the requests" of robots that only guessed public job pages: a time coincidence that designates members wrongly.
- Changes:
  - New constant CLOUD_ORG_RE (names of hosting providers and a few generic words of the trade: hosting, datacenter, colocation), matched on the organisation, the network name and the abuse mailbox of the block.
  - New function reseau_lire IP: reads the owner of the block through apps/_reseau.py (RDAP, whois, cache of addresses) into RESEAU_ORG, RESEAU_NET, RESEAU_PLAGE, RESEAU_PAYS, RESEAU_ABUS, RESEAU_REGISTRE, RESEAU_SOURCE, without display. infos_reseau() uses it (same display as before).
  - New function reseau_hebergeur: 0 when that owner is a hosting provider.
  - CLOUD_PTR_RE moved up, next to these functions (defined before the --ban block, which will use them).
  - investigate_and_propose(): clue "Serveur loué chez un hébergeur : ORGANISATION (propriétaire du bloc, RDAP ; DNS inverse : ...)" when the PTR does not match but the owner does (--investigate only: the daily report makes no RDAP query). Odoo accounts (comptes_bd_ip) searched only when the requested URLs include a session page (/web/login, /web/session, /web/dataset, /web/action, /web/webclient, /web/signup, /web/reset_password, /web, /odoo, /my, /mail/, /discuss/, /bus/, /websocket, /longpolling, with or without language prefix); otherwise one line says why they were not searched.
  - lang/nginx-log-audit.en.po: the new messages.
  - doc/fr and doc/en 02-nginx-log-audit.md: the two rules.
  - nginx-tools-tests/test_nginx_log_audit.py: new class ChkNginxLogs272 (owner Vultr from a simulated RDAP answer, owner unknown, accounts searched or not); test_ban_gate.py: version.
- Bugs fixed:
  - Symptom: "[ ] Serveur loué : valtrona.eu" for an address of Vultr. Diagnosis: only the reverse DNS was compared with CLOUD_PTR_RE. Fix: the owner of the block, already read by --investigate, is compared too.
  - Symptom: members of the site listed for robots that never logged in. Diagnosis: comptes_bd_ip correlates the time of the requests with the sessions in the database; Odoo does not record the address of a session. Fix: only after a request that needs a session.
- Safeguards and edge cases: the score can rise by 1 for a hosted address whose reverse DNS does not show the provider (140.82.7.85: 1 -> 2/7, still under the threshold of 3); the daily report and --unban-check are unchanged (no RDAP query there). A member behind a VPN at a hosting provider who uses the back office still gets the list (session pages requested). Logins recorded in the Odoo journal for the address itself (logins_odoo) are always shown. Unknown owner (no RDAP, no whois): clue not checked, as before. Generic words are limited to hosting, datacenter and colocation, to avoid catching access providers.
- Checks performed: bash -n; ChkNginxLogs272 (3 tests) [OK]; the new messages have their English entry (the other missing entries of lang/nginx-log-audit.en.po already exist on main).
- Action required: none.

### 2.69.20261101.234513 - Fail2ban section lists the banned addresses, not only their number

- Title: the fail2ban check of the "AUTRES POINTS A RE-VERIFIER" report now shows the banned addresses of each jail.
- Reason: the report gave the number of banned addresses per jail (for example "4 IP bannies en ce moment") but not the addresses, so the administrator had to run fail2ban-client status for each jail by hand to check them.
- Changes: revue_controles(), section 2 (jails fail2ban): the line "Banned IP list" of fail2ban-client status <jail> is printed under the count of each jail. Read-only, no change of ban.
- Bugs fixed: none (enhancement).
- Safeguards and edge cases: if a jail has no banned address, nothing more is printed. The count line is unchanged.
- Checks performed: bash -n on nginx-log-audit.sh. No new text is displayed, so the translation catalogues are unchanged.
- Action required: none.
### 2.71.20261101.231500 - Retour arrière : écho et effacement rétablis avant chaque réponse

- Title: the answer questions (demander_oui, demander_texte, the ban exception word) restore echo and erase first.
- Reason: Request of the administrator: in nginx-hardening.sh, at the prompt "Faire le setup du courriel (relais SMTP) maintenant ? [o/N] :", the Backspace key shows "d^H^H^H^H" and erases nothing. The same problem can hit every program that asks a question, so every interactive prompt of the Bash and Python programs must be checked and fixed.
- Changes: tty_ligne placed before the four interactive reads: the fallback of demander_oui (read -r -p), the read -e of demander_oui and demander_texte (in their subshells), and the BANNIR confirmation (read -r -e -p). Fallback definition after apps/_i18n.sh is loaded. The sum of this change is independent of the recidivist section of 2.71 (PR 150): if PR 150 is merged first, the version lines conflict and the newer one is kept.
- Bugs fixed: same symptom as nginx-hardening.sh 2.74 (erase shows ^H). Diagnosis and fix as in apps/_i18n.py 1.22.
- Safeguards and edge cases: Without a terminal (pipe, cron, stdin not a tty): nothing is changed, the programs behave as before. Stdin and /dev/tty redirections are guarded with || true (set -e). Password prompts (read -s) are not changed. The helper is defined in apps/_i18n.sh; a program without that file gets a no-op fallback. The BANNIR typing is unchanged in its rule (it still refuses without a terminal).
- Checks performed: bash -n; nginx-tools-tests/test_saisie_terminal.py (new, static): every interactive read -p / read -e of the Bash programs has tty_ligne on its line; tty_ligne is defined and sets icanon echo echoe; saisie() is defined and used by the i18n context; apps/_menu.py has its own line reader; versions.
- Action required from the user: none.
### 2.71.20261101.222709 - Repeat offenders are investigated, never banned in this report

- Title: the section "Récidivistes fail2ban à surveiller" investigates each repeat offender and no longer bans from the report.
- Reason: on 2026-11-01 the report of 132.196.59.85 and 45.138.12.41 said "Bannissement PERMANENT recommandé" and offered the ban on the recurrence alone (fail2ban bans expire, then the same address comes back). The investigation of 132.196.59.85 gave 0/7. The section also called confirm_and_ban, a question that did not pass through the investigation.
- Changes:
  - nginx-log-audit.sh, section of the repeat offenders: the call to confirm_and_ban is removed. Each address runs --investigate ... --no-prompt; the command nginx-log-audit.sh --ban IP is shown only if the investigation recommends the ban (score 3/7 or more). Otherwise the line says "à surveiller".
  - The wording of the header and of the explanation is corrected: a ban is never made here, and "définitivement" is removed (a ban is reversible with --unban).
  - lang/nginx-log-audit.en.po: the old entries are replaced; the English texts of the new lines are added.
  - nginx-tools-tests/test_ban_gate.py: static test (no confirm_and_ban in the section, investigation and score check present); version 2.71.
  - nginx-tools-tests/test_nginx_log_audit.py and test_i18n.py: header text updated.
  - web-monitor.py 2.84 reads the new header (see its CHANGELOG entry).
- Bugs fixed: symptom: the report offered a permanent ban on recurrence alone, with a question that bypassed the investigation. Diagnosis: the section was written before the investigation gate (2.69/2.70). Fix: see above.
- Safeguards and edge cases:
  - The investigation is run with --no-prompt: no question is asked by the report.
  - An investigation that fails (empty output) is shown as "à surveiller", never as a ban.
  - --ban still runs its own gate (2.70): the score and the confirmation are required.
- Checks: test_ban_gate (10 tests OK, after the update); test_nginx_log_audit and test_i18n adapted (see the pull request for the results).
- Action required: none. For 132.196.59.85 and 45.138.12.41, read the investigation line and answer N unless the score is 3/7 or more.

### 2.70.20261101.215908 - A ban needs the investigation score, not only the evidence

- Title: --ban is refused unless the investigation recommends the ban (score 3/7 or more), and three weak signals no longer count as evidence.
- Reason: on 2026-11-01, --ban 132.196.59.85 said "Verdict : bannissement justifié" while the investigation in the same report gave 0/7 with "aucun signe d'hostilité". The gate of 2.69 accepted the evidence verdict alone, which made the two verdicts contradict each other.
- Diagnosis:
  - The fail2ban recidivism was counted as evidence "for". It comes from the same requests as the ones it is supposed to justify (circular).
  - The sensitive-files pattern matched any ".php" in the URL, so /md5.php3 (a plain 404) was counted as an attempt to reach sensitive files.
  - The gate tested PREUVES_VERDICT "justifie" or the score; the verdict alone was enough.
- Changes:
  - nginx-log-audit.sh, preuves_ip: the fail2ban recidivism goes to the weak hints ("Indice faible"), never to the evidence "for".
  - nginx-log-audit.sh, sensitive-files pattern: ".php" replaced by "\.php([?]|$)" (a PHP page, not php3 or other suffixes).
  - nginx-log-audit.sh, --ban gate: refused unless BAN_RECOMMANDE=1 (investigation score 3/7). The exception (--reason, then BANNIR on a terminal) is unchanged.
  - Evidence verdict line: "Preuves : pas de raison contraire trouvée" with a reminder that the score of 3/7 is also required (the label "Verdict : bannissement justifié" is removed).
  - nginx-tools-tests/test_ban_gate.py: static tests updated (gate condition, recidivism not evidence, .php pattern); version 2.70.
  - nginx-tools-tests/test_nginx_log_audit.py: ban scenarios use sensitive-file probes (20 requests from the address) instead of SQL injection only, which does not reach the score alone; labels updated.
- Bugs fixed:
  - Symptom: a ban recommended with the investigation at 0/7 and "bannissement justifié" in the same report.
  - Diagnosis and fix: see above.
- Safeguards and edge cases:
  - Evidence alone never bans; the investigation score is required, as in CLAUDE.md (threshold 3).
  - The exception path is unchanged: --reason, then BANNIR typed on a terminal; --yes does not bypass it.
  - The count of sensitive requests now ignores plain .php3/.php4 suffixes; genuine probes of WordPress and .env paths are still counted.
- Checks: test_ban_gate (9 tests OK); test_nginx_log_audit (50 tests OK); bash -n OK.
- Action required: web-monitor.py still recommends bans from recidivism without the investigation; that is a separate pull request to come. Do not ban 132.196.59.85 (answer N).

### 2.69.20261101.204354 - No bulk ban: every ban re-checked, evidence required, typed exception

- Title: no program bans several addresses at once any more. Each --ban runs the full investigation first and is refused unless the evidence justifies it; the only exception is a typed confirmation.
- Reason: on 2026-11-01 the address 62.34.251.225 was banned by --ban-sqli in a group, with a recorded justification that the logs contradict (its only request that day was an ordinary page). The user asked that no ban be made in bulk and that every ban be re-validated with --investigate, with a detailed justification.
- Changes:
  - nginx-log-audit.sh, preuves_ip: the SQL injection lines of the site log are evidence FOR a ban (counted over all rotations). The function sets PREUVES_VERDICT: "justifie" (evidence for, no strong reason against), "examiner" (both), or "aucune" (no evidence for).
  - nginx-log-audit.sh, --ban: preuves_ip always runs, even with --yes, and the investigation is always shown. The ban is refused unless PREUVES_VERDICT is "justifie" or the investigation recommends it (score of at least 3/7, the threshold of CLAUDE.md).
  - Exception: --reason TEXT, then the word BANNIR typed by hand on a terminal. --yes does not bypass the gate. Without a terminal the exception is refused. The reason is recorded with the prefix "EXCEPTION (verdict ...)".
  - nginx-log-audit.sh, --ban-sqli: --yes is refused. Without a terminal the program only lists the addresses and bans nothing. On a terminal, each address goes through --ban one by one (the group question is removed).
  - SQLI_RE is defined near the top of the script (see bugs fixed).
  - nginx-tools-tests/test_ban_gate.py (new): 7 static tests (evidence always verified, refusal condition, exception requires reason, terminal and BANNIR, confirmation skipped only with the exception, SQL injections counted as evidence, --ban-sqli without --yes and without group question, version string).
  - nginx-tools-tests/test_nginx_log_audit.py: 5 ban scenarios adapted to the gate. Evidence added where a ban is expected (helper _preuves_sqli, three SQL injection requests with 404). The reasoning test now asserts the refusal. The --ban-sqli test asserts the listing without insertion and the refusal of --yes. Listing text updated to the current wording. Import test: evidence for 198.51.100.99.
- Bugs fixed:
  - Symptom: --ban stopped silently after the line "Site : N requêtes" with exit code 1 and no message.
  - Diagnosis: SQLI_RE was defined at the end of the script, but the --ban path (preuves_ip) runs before that point. With set -u, the unbound variable aborted the script. This bug was in the unreleased 2.69 draft; the tests found it before any commit.
  - Fix: SQLI_RE is defined right after set -euo pipefail.
- Safeguards and edge cases:
  - A ban without a terminal and without the exception is always refused, whatever --yes says.
  - The investigation recommendation is accepted only with the score of CLAUDE.md (3/7); a score of 2/7 or less does not authorise a ban.
  - An address with strong reasons against (for example normal navigation) is never "justifie" on the injections alone.
  - fail2ban and CrowdSec automatic bans are unchanged (decision: automatic, with a daily review, not yet implemented).
  - web-monitor.py and app-log-live.py are not changed by this version. They still call --ban IP --yes, so until their own pull requests are merged, their bans are refused when there is no evidence. This is intended.
- Checks: test_nginx_log_audit (50 tests OK, awk); test_ban_gate (7 tests OK); bash -n OK; ruff clean on test_ban_gate.py. The full run-all.sh still shows failures that are not caused by this change (see the pull request description). --ban-sqli has not been tested on a real terminal with real logs.
- Action required: do not lift 62.34.251.225 without a fresh --investigate. Use --ban only on a terminal, one address at a time. Until web-monitor.py and app-log-live.py are updated, their ban buttons will be refused without evidence.

### 2.68.20261101.195800 - SQL injection kept as a reason to ban; encoded parentheses recognized

- Title: an address with an SQL injection in the logs is never proposed for lifting by --unban-check or --unban-low-score; the injection pattern now also matches encoded parentheses.
- Reason: on 2026-11-01, --unban-check proposed lifting 37.65.66.209, banned on 2026-10-28 by --ban-sqli for SQL injection (URL with UNION ALL SELECT and EXTRACTVALUE). The score was 0/7 because the score does not count injections, and the EXTRACTVALUE requests were not recognized at all.
- Diagnosis:
  - decide_unban judged only the score criteria (burst, scripts, errors, sensitive files, catch-all). An injection gives 200 responses and triggers none of them.
  - SQLI_RE required a literal parenthesis after EXTRACTVALUE, UPDATEXML, ELT, CONCAT, SLEEP and BENCHMARK. Browsers and the log send it encoded as %28, so those requests were missed. The UNION SELECT request was recognized, which is why the ban itself was justified.
- Changes:
  - nginx-log-audit.sh: SQLI_RE accepts ( or %28 after the function names. New function sqli_hits_ip (counts the lines of the full history, INV_SRC, from one address that match SQLI_RE). decide_unban calls it first: if there is a hit, the verdict is "garder" with the message "injection SQL dans les journaux", before any other criterion (protection, search engine, score, login). Used by --unban-check and --unban-low-score.
  - nginx-tools-tests/test_sqli_unban.py (new): 5 tests, including the three URL of 37.65.66.209 and normal URL that must not match.
- Bugs fixed: a banned attacker proposed for lifting (see diagnosis).
- Safeguards and edge cases:
  - A literal parenthesis still matches (no regression).
  - Ordinary URL with order=... and asc do not match.
  - The check reads the full history (all rotations), so an old injection keeps the ban.
  - decide_unban is the only place that decides, so the interactive question and --unban-low-score cannot lift an address with an injection.
- Checks: test_sqli_unban (5 tests OK); test_nginx_log_audit (50 tests OK); sqli_hits_ip run on a sample access log (2 hits, 0 for a normal address, 0 for an unknown address); bash -n OK.
- Action required: do not lift 37.65.66.209. Other addresses banned earlier for SQL injection are kept after this version; check the list with --unban-check before any --unban-low-score --yes.
 - Lift the bans of Cloudflare addresses (option --unban-cdn)

- Title: new option --unban-cdn lifts, in one operation, the bans (fail2ban and manual firewall) of addresses inside Cloudflare's published ranges, after a preview and one confirmation.
- Reason: on 2026-11-01 a Cloudflare node was banned by mistake (nginx-badrequests jail, 14 ordinary 404 and 30x responses). Other Cloudflare addresses may have been banned the same way. Lifting them one by one with --unban and fail2ban-client was slow and error-prone.
- Changes:
  - nginx-log-audit.sh: new option --unban-cdn (root required). Variable DO_UNBAN_CDN, block placed before --investigate. It collects the current bans (fail2ban jails and manual firewall rules), keeps those inside nginx/cdn/cloudflare-ips.txt (one python3 call for IPv4 and IPv6), and shows a preview table: address, range, source, decision.
  - Confirmation: one question for the whole set ([o/N]). With --yes, no question. Without a terminal, the preview is shown and nothing is lifted.
  - Lifting: fail2ban bans with fail2ban-client set JAIL unbanip; manual firewall bans with --unban --yes and the reason "bannissement Cloudflare levé (--unban-cdn)" (recorded in bans.tsv).
  - Help text (--help), usage line and header comment updated. The option is listed before --unban-check (alphabetical order).
- Bugs fixed: none. Missing feature.
- Safeguards and edge cases:
  - Protected addresses (protected_ip_reason: loopback, private networks, white list and [protected] places) are shown as "protégée : jamais levée" and never lifted.
  - Addresses outside the listed ranges are never touched, even if they belong to another CDN.
  - If nginx does not yet read CF-Connecting-IP (no set_real_ip_from in /etc/nginx/snippets/cdn-realip.conf), a warning is shown before the preview: a lifted address can be banned again. Deploy --cdn cloudflare first.
  - Root is required; a failing fail2ban unbanip or --unban is counted and gives exit code 1.
  - Without a confirmation, nothing is changed.
- Checks: bash -n on the script; --version and --help show the new option; the range matching was run on 104.28.221.220 (now matched by 104.16.0.0/12), 172.64.1.1 (matched) and 8.8.8.8 (not matched); the protection check was read in the code. Not run: a real lift on a server (needs root and fail2ban/ufw).
- Depends on: the Cloudflare ranges of nginx/cdn/cloudflare-ips.txt, added by PR 141 (feature/cf-connecting-ip). Merge PR 141 first.
- Action required: after merge, run `sudo nginx-log-audit.sh --unban-cdn` to see the preview, then answer [o/N].

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

### 1.32.20261109.153000 - --status works without root

- Title: --status runs as an ordinary user and says what it cannot show.
- Reason: request of the administrator on 2026-11-09 ([2]).
- Changes: --status no longer refused without root; notice "Droits limités (pas root) : non disponible : contenu des ipset et règles du pare-feu ..."; the ipset and firewall rule loops are skipped; lang/sync-crowdsec-blocklist.en.po.
- Bugs fixed: none.
- Safeguards and edge cases: the operations that change the firewall still need root.
- Checks performed: ShellCheck 0.11.0 [OK]; manual run as an ordinary user [OK].
- Action required: none.

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

## system-hardening.sh

### 1.1.20261105.081634 - AIDE: SHA-512 instead of every checksum compiled in

- Title: --update sets Checksums = sha512 in /etc/aide/aide.conf instead of Checksums = H.
- Reason: question of the administrator on 2026-11-05: why several checksums in the AIDE configuration, it is very long and SHA-512 should be enough ("H specifies that all checksums compiled in are used").
- Changes: new configuration key AIDE_CHECKSUMS (sha512 by default, keep = the distribution value); new functions aide_checksums_now(), aide_checksums_set(), aide_checksums_restore(), aide_checksums_check(); aide_check() reports the current value (warning for H); aide_apply() changes the line, then creates the baseline again when the checksums changed (old one kept as aide.db.previous); rollback() puts the old line back. Files: system-hardening.sh, doc/en and doc/fr system-hardening.conf.example and 19-system-hardening.md, tests.
- Bugs fixed: symptom: the creation and the daily check of the AIDE baseline took a long time and a lot of processor. Diagnosis: Checksums = H computes every checksum compiled in AIDE (md5, sha1, sha256, sha512, rmd160, tiger, whirlpool, gost...) for every file. Fix: SHA-512 alone, which is enough to detect a changed file.
- Safeguards and edge cases: the line is changed where it is (the groups of aide.conf take the value of Checksums when they are defined: a definition in aide.conf.d would change nothing); the old line is kept in a comment above it and --rollback restores the file exactly; no change when there is no Checksums line or when the value is already the one wanted; a baseline made with the old checksums is never kept (every file would be reported as changed), it is renamed aide.db.previous and a message says to read the last AIDE report first; aide.conf is a conffile of the package: an upgrade of aide keeps the changed file (dpkg asks, unattended-upgrades keeps it).
- Checks performed: shellcheck 0.11.0 (no finding); test_condenses_d_aide_sha512_et_retour_arriere, test_condenses_d_aide_gardes_avec_keep; test_system_hardening (17 tests).
- Action required from the user: none; the next sudo system-hardening.sh --update changes the line and creates the baseline again (5 to 30 minutes, shorter than before).

### 1.0.20261104.185853 - First version: security updates, audit and file integrity of the system

- Title: new program system-hardening.sh: hardening of the operating system on a Proxmox VE 9 host (Debian 13), a virtual machine (Ubuntu 20.04 and later, Debian 12 and later) or an LXC container (Debian 12 and later).
- Reason: request of the administrator on 2026-11-04, after the discussion about an EDR (Wazuh, Falco, osquery): start with unattended-upgrades for the security updates, auditd with a few rules (sudo, SSH keys, cron, /etc) and AIDE for file integrity, in a separate program (not nginx-hardening.sh: these settings concern every machine, the Proxmox host included, which has no nginx) whose name does not suggest the host of a container.
- Changes:
  - Check only by default (--check); --update applies; --rollback removes the files written; --baseline-update accepts the current files as the new AIDE baseline; --notify prints the daily summary and mails it when something needs attention; --menu (apps/_menu.sh); --lang; --changelog; --report-err; --version; -c/--config; -v/--verbose. Options sorted alphabetically and in colour, messages in French and English.
  - Detection: /etc/os-release (Debian 12+, Ubuntu 20.04+), systemd-detect-virt (LXC container, VM), pveversion (Proxmox host); another system: check only, --update refused.
  - unattended-upgrades: own file 52rlq-unattended-upgrades that clears the lists of 50unattended-upgrades and keeps the security origins only (Debian Security; Ubuntu security, ESM apps and infra), Automatic-Reboot from AUTOMATIC_REBOOT (no by default) at AUTOMATIC_REBOOT_TIME; apt-daily timers enabled; pending security updates counted with apt-get -s; reboot pending (reboot-required, or a newer kernel in /lib/modules than the running one, not in a container).
  - auditd (not in a container): own file 60-rlq-hardening.rules with the keys rlq-sudo, rlq-sudo-exec, rlq-ssh-keys (root and every user), rlq-sshd, rlq-cron, rlq-identity, rlq-pam, rlq-preload, rlq-systemd, rlq-apt; only existing paths; augenrules --load; on a Proxmox host, watches on the sensitive files of each running container (/var/lib/lxc/ID/rootfs, AUDIT_WATCH_CONTAINERS); events of the last 24 h counted with ausearch.
  - AIDE: own file 99_rlq_exclusions (logs, caches, PostgreSQL, Docker, BigBlueButton, Odoo filestore and the data_dir of the Odoo configurations found, Proxmox storage and /etc/pve, AIDE_EXCLUDE); update-aide.conf when present (Ubuntu 20.04); aide --config-check; baseline with aideinit; daily check of the distribution (dailyaidecheck.timer or /etc/cron.daily/aide) and its last result read in /var/log/aide/aide.log.
  - Daily summary: system-hardening-notify.service and .timer (NOTIFY_TIME, 07:30 by default) run --notify; the mail goes through apps/_courriel.py with the mail settings of the suite (nginx-tools-mail.conf), only when something needs attention (security updates installed, reboot pending, AIDE differences, sensitive audit events) or every day with NOTIFY_ALWAYS=yes.
  - Configuration keys: LANGUAGE, VERBOSE, UNATTENDED_UPGRADES, AUTOMATIC_REBOOT, AUTOMATIC_REBOOT_TIME, AUDITD, AUDIT_WATCH_CONTAINERS, AIDE, AIDE_EXCLUDE, NOTIFY, NOTIFY_TIME, NOTIFY_ALWAYS.
  - Files: system-hardening.sh, doc/en and doc/fr system-hardening.conf.example and 19-system-hardening.md, doc/en and doc/fr 00-overview.md, nginx-tools-tests/test_system_hardening.py, test_conventions.py and test_menu.py (program registered).
- Bugs fixed: none (new program).
- Safeguards and edge cases: no file of the distribution is modified (only files of its own, rewritten only when their content changes); --rollback keeps the packages and the AIDE database; a missing path is never put in the audit rules (augenrules would refuse the whole set); no automatic reboot unless AUTOMATIC_REBOOT=yes; on a Proxmox host only the Debian security updates are applied (the Proxmox packages are updated by hand); invalid times in the configuration are reported and the defaults kept; the mail never needs a local mail server; without root, the loaded rules are reported as not checked.
- Checks performed: shellcheck 0.11.0 (no finding); nginx-tools-tests/test_system_hardening.py (LXC Debian 12, Proxmox Debian 13, Ubuntu 20.04 VM, unsupported system, without root, configuration, English, idempotence, rollback, AIDE baseline, daily summary with and without mail); convention and menu tests; doc/build_docs.py --check.
- Action required from the user: none to install. To use it: sudo system-hardening.sh (check), then sudo system-hardening.sh --update on each machine, the Proxmox host included; the daily mail needs the mail settings of the suite (nginx-hardening.sh --update --mail-setup).

## apps/_theme.py

### 1.0.20261103.112517 - Color themes shared by the programs

- Title: Color themes shared by the programs.
- Reason: request of the administrator on 2026-11-03: a --theme N option for all the programs (dark background, light background, etc.), making sure that every color reads on the chosen background. Delivered first for app-log-live.py, web-monitor.py and nginx-log-audit.sh; the other programs follow on request.
- Changes:
  - New module apps/_theme.py: themes 0 (terminal colors), 1 (dark background), 2 (light background), 3 and 4 (high contrast). sgr(code) replaces each color of an SGR code by the nearest color of the 256-color palette whose WCAG contrast with the background of the theme reaches 4.5 (themes 1 and 2) or 7 (themes 3 and 4); a reverse video becomes an explicit text and background; faint text becomes a gray that reads; a background gets a black or white text.
  - Command line: --demo [N] (each theme drawn on its reference background), --bash N (variables for the bash programs), --sgr N CODE.
  - Reference backgrounds: #262626 (dark) and #eeeeee (light), the worst plausible ones; a pure black or white background reads better.
- Bugs fixed: none.
- Safeguards and edge cases: theme 0 returns every code unchanged; a value outside 0 to 4 is an error (parse_theme); an invalid NGINX_TOOLS_THEME in the environment means theme 0; no color is written by the module itself except in --demo.
- Checks performed: test_theme.py checks, for each theme, the contrast of every color code written by app-log-live.py, web-monitor.py and nginx-log-audit.sh (and of the style tables), reverse videos, backgrounds, priority of the sources.
- Action required from the user: none.

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

## apps/_advisor.py

### 1.16.20261109.234500 - Static files slow without SQL: waiting for the disk; one timeline line per interruption; most often: present findings only

- Title: the slow static files and images explain the slow requests as a wait for the disk; the timeline lists each interruption of nginx; « Problems seen most often » cites only findings still present.
- Reason: exports of DEV and PROD of 2026-11-09 23:35 with app-log-live.py 1.187 and apps/_advisor.py 1.15.
- Changes: new FILE_RE (/static/, /web/image, /web/content, image, font, css and js files); rule_slow(): evidence « {k} slow requests are static files or images with almost no SQL ... » and the cause « waiting for the disk » when they are half of the slow requests or more; timeline(): one « nginx: Odoo unreachable » entry per interruption (times of app-log-live.py 1.187); History.record(): top limited to the findings of this analysis; lang/_advisor.fr.po; nginx-tools-tests/test_advisor.py: test_116_fichiers_statiques_lents_attente_du_disque, test_116_plus_souvent_seulement_les_constats_presents, test_nouveau_recurrent_calme_regle_priorites updated.
- Bugs fixed:
  - symptom: PROD cause « temps passé hors de la base de données : pages lourdes, trop peu ou trop de workers » while 11 of the 20 slow requests were static files of 9 to 10 s without SQL; fix: they are recognised.
  - symptom: timeline « Odoo injoignable, début (49 refus jusqu'à 22:55:15) » for three short interruptions; fix: one line each.
  - symptom: DEV « Problèmes vus le plus souvent » listed errors gone for a week (5xx on /en_CA/web/login, Missing model); fix: present findings only.
- Safeguards and edge cases: a page whose time is SQL is never counted as a file.
- Checks performed: test_advisor [OK].
- Action required: none.

### 1.15.20261109.233000 - Findings corrected after the DEV and PROD exports of 2026-11-09

- Title: interruptions of nginx cut, slow requests grouped in one window, slow requests during the backup, probes of this server out of the severity, gevent advice escalated, workers bound as step 6.
- Reason: analysis of the DEV and PROD exports of 2026-11-09 23:08 asked by the administrator.
- Changes: rule_nginx_upstream(): « {k} interruptions, {n} refused connections: » with each interruption (times of app-log-live.py 1.187); rule_slow(): largest group inside ONE window of SIMULTANEOUS_S seconds; slow requests during a run of odoo-backup.service (evidence and new cause « the backup of the suite was running »); severity counts neither the probes of this server (127.0.0.1, server_ips) nor the cold cache of the 10 minutes after a start (line « Counted in the severity: k of n »); _gevent_limits(): restarts since the start of Odoo; already at 2048 / 2560 and restarted: 1.5 times the values; the « MB more of real RAM » line only when it is more; odoo_settings_advice(): « few » bounded like nginx-hardening.sh 2.93 step 6 (limit_memory_hard 1536 MB, 400 MB without RAM); lang/_advisor.fr.po (the old « about 325 MB each » text removed).
- Bugs fixed:
  - symptom: PROD « 16 requêtes lentes sur des pages différentes en 73787 s »; diagnosis: the pairs under 60 s were chained over the whole day; fix: one window.
  - symptom: PROD gevent finding repeating the values already set (2048 / 2560) with « au plus environ 0 Mo de RAM de plus »; diagnosis: restarts of the whole period and no check of the values in place; fix: since the start, escalation, line only when useful.
  - symptom: DEV « ✖ Requêtes lentes : 6 » for 6 probes of app-health-check.py on a cold Odoo; fix: INFO when nothing else is slow.
  - symptom: DEV « jusqu'à 13 workers sont possibles (environ 325 Mo chacun) » against 7 recommended by nginx-hardening.sh; fix: same bound.
- Safeguards and edge cases: a slow request of a real visitor still counts; without backup events nothing changes.
- Checks performed: test_advisor (71 tests, test_115_analyse_dev_prod_20261109) [OK].
- Action required: none.

### 1.14.20261109.221500 - Cause « waiting for the disk » for the slow requests

- Title: slow requests that end together with almost no SQL are explained as a wait for the disk.
- Reason: request of the administrator on 2026-11-09: the LXC container of Odoo 18 CE now has 32 GB; make the scripts set the right parameters so that nginx and PostgreSQL use the disk less (SATA disks, reads of 160 to 230 ms measured by host-perf-audit.py); check the buffers and the cache of the images in nginx-hardening.sh; a cause « waiting for the disk » in the analysis of app-log-live when several workers end together without SQL.
- Changes: new constant TOGETHER_S (2 s) and function ended_together() (largest group of at least 3 slow requests ending within 2 s, each with less than 10 % of SQL and 2 s or more outside SQL); rule_slow(): evidence "{k} slow requests ended in the same 2 seconds ...", new cause "waiting for the disk" with the advice host-perf-audit.py on the host, nginx-hardening.sh --update, an SSD (ZFS special vdev or L2ARC); lang/_advisor.fr.po.
- Bugs fixed: none.
- Safeguards and edge cases: the cold cache after a restart and the database busy stay first; the cause is chosen only when these requests are half of the slow ones or more.
- Checks performed: test_advisor test_attente_du_disque [OK].
- Action required: none.

### 1.13.20261109.211500 - Finding odoo-conf-check

- Title: the analysis reports the errors of odoo.conf found by apps/_odoo_conf_check.py.
- Reason: request of the administrator on 2026-11-09: Odoo refused "limit_memory_soft_gevent = 2147483648 # (2048 Mo" (comment after the value); is there a program that checks the configuration of Odoo, or can one be written.
- Changes: new rule rule_odoo_conf_check() (finding odoo-conf-check: PROBLEM with errors, LOOK with warnings only, 8 lines at most, the command to check again); lang/_advisor.fr.po.
- Bugs fixed: none.
- Safeguards and edge cases: no finding without details["odoo_conf_check"].
- Checks performed: test_odoo_conf_check.test_constat_de_l_analyse, test_advisor [OK].
- Action required: none.

### 1.12.20261109.204500 - Live chat limits (gevent), memory to add, memory nearly used up

- Title: new findings gevent-memory-limit and memory-low-now; the memory risk says how much memory to add.
- Reason: request of the administrator on 2026-11-09: check limit_memory_soft_gevent / limit_memory_hard_gevent and say what raising them is for (more people chatting at the same time); recommend more memory when the RAM is short.
- Changes: new constants COMFORT_HARD_MB (1536), GEVENT_SOFT_MB, GEVENT_HARD_MB (2048 / 2560); new function ram_needed(); memory_plan() returns ram_needed; new methods _gevent_limits() (finding gevent-memory-limit: INFO, LOOK and confirmed when the Odoo log shows « Gevent virtual memory limit reached ») and _memory_low_now() (finding memory-low-now, LOOK, when MemAvailable is under 15 %); rule_memory(): advice "add about N GB of memory" when the plan is under 1536 MB; lang/_advisor.fr.po.
- Bugs fixed: none.
- Safeguards and edge cases: "False" (Odoo's value for not set) is read as not set; nothing about gevent without workers (one process).
- Checks performed: test_advisor test_gevent_et_ram_juste [OK].
- Action required: none.

### 1.11.20261109.194500 - Memory risk in virtual memory, workers recycled at birth

- Title: the memory risk and its advice use the virtual memory of the workers; new finding memory-limit-too-low.
- Reason: report of the administrator on 2026-11-09 (PROD workers recycled in a loop).
- Changes: new function memory_plan() and constants VIRTUAL_OVERHEAD_MB, IDLE_WORKER_VMS_MB, SOFT_FLOOR_MB (same calculation as nginx-hardening.sh 2.85); rule_memory(): worst case in RAM (limit_memory_hard minus the virtual overhead), advice with the plan, "about N workers at most" when the memory is too short (title "Too many Odoo workers for the memory of the server"); new finding memory-limit-too-low (PROBLEM) when limit_memory_soft is under a worker at rest or when workers stopped before their first request, advice in bytes; lang/_advisor.fr.po.
- Bugs fixed: symptom: on PROD (13 workers, 16 GB) the Odoo log showed "Worker (N) virtual memory limit (691601408) reached" then "exiting. request_count: 0" several times per second, no worker survived; diagnosis: Odoo compares limit_memory_soft with the VIRTUAL memory of a worker (psutil vms; limit_memory_hard is RLIMIT_AS), and step 6 / the memory risk shared the RAM as if these limits were RAM: 768 MB hard and 652 MB soft were suggested, under the 660 MB of virtual memory of a worker at rest (RSS 250 MB); fix: limit = RAM share + virtual overhead (measured, about 400 MB), limit_memory_soft never under max(1024 MB, 1.5 x a worker at rest), fewer workers suggested when the memory is too short.
- Safeguards and edge cases: without measurement, 700 MB at rest and 400 MB of overhead; the finding is confirmed only when the Odoo log shows the recyclings.
- Checks performed: test_advisor (test_risque_de_memoire updated, test_workers_recycles_a_la_naissance) [OK].
- Action required: none.

### 1.10.20261109.153000 - Odoo configuration in effect, Odoo parameters in the e-mail findings, backups in the timeline

- Title: the analysis says when odoo.conf is not in effect, and shows the Odoo mail parameters themselves.
- Reason: request of the administrator on 2026-11-09 ([1] and [3]).
- Changes:
  - New rule rule_odoo_runtime(): findings odoo-conf-not-applied (LOOK when values changed since the start, INFO when the file changed without a snapshot), odoo-conf-command-line (INFO, options of run.sh or of the unit override odoo.conf), odoo-processes (INFO, fewer processes than the configuration gives).
  - rule_mails(): evidence "Odoo parameters now: ..." (mail.session.batch.size, mail.mail.queue.batch.size, mail.mail.force.send.limit) with "(not set: Odoo default)".
  - timeline(): "backup: " events of odoo-backup.service. Restart advice names the real service.
  - lang/_advisor.fr.po: the new messages. nginx-tools-tests/test_advisor.py: class OdooRuntime110.
- Bugs fixed: none.
- Safeguards and edge cases: no finding without details["odoo_runtime"]; at most 10 lines of evidence.
- Checks performed: test_advisor (68 tests with test_app_log_live.OdooRuntime181) [OK].
- Action required: none.

### 1.9.20261109.110500 - Findings checked by an administrator, Odoo device log, SMTP limit per session

- Title: codes on the findings, list of the findings checked by an administrator, sessions of the Odoo device log.
- Reason: see app-log-live.py 1.180.
- Changes (apps/_advisor.py, lang/_advisor.fr.po, nginx-tools-tests/test_advisor.py):
  - New ack_code(), Acknowledgements (acknowledged.json: load, active, add, remove, save in mode 600), split_acknowledged() (ACK_GROWTH = 2), constant ACK_FILE.
  - render(): the code of each finding after its title; new argument acknowledged: section "Checked by an administrator, left out of the summary"; a checked finding whose count more than doubled is shown again with the date of the check.
  - rule_hot_pairs(): the sessions of details["devices"]; a loop of the back office from the session of a user of the site is an information with a confirmed cause and the --ack command.
  - rule_bans(): an address where a user of the site has an Odoo session is taken out of the bans proposed (and out of the --apply correction); new finding "ban-held-session".
  - SMTP_HINTS: the track of the limit per SMTP connection says "for example 3" and explains that Odoo then opens a new connection every 3 e-mails.
- Bugs fixed: none.
- Safeguards and edge cases: an unreadable acknowledged.json is ignored (nothing is hidden); "all-clear" is never hidden; a portal account does not protect an address from a ban (only users of the site).
- Checks performed: test_advisor (64 tests, class Version19 added) [OK]; catalogue complete and without stale entries.
- Action required: none.

### 1.8.20261109.100500 - Verification of the DEV and PROD exports: memory rule of nginx-hardening, SMTP limit per session, CSRF, future events

- Title: the analysis agrees with nginx-hardening.sh on the memory limits and explains the e-mails refused on PROD.
- Reason: verification on 2026-11-09 of the first exports of DEV and PROD (see app-log-live.py 1.179).
- Changes (apps/_advisor.py, lang/_advisor.fr.po, nginx-tools-tests/test_advisor.py):
  - rule_memory(): reserve = max(15 % of the memory, memory used outside Odoo now), margin = max(512 MB, 10 %), the rest shared by workers + cron + 1 gevent (as nginx-hardening.sh 2.82); the memory used outside Odoo is shown.
  - SMTP_HINTS: new first track for "4.4.5 / messages per session" (system parameter mail.session.batch.size).
  - rule_mails(): number of recipients when more than three; "before the window, still not resent".
  - KNOWN_MESSAGES: "No CSRF validation token provided" and "dbfilter rejects it" (information).
  - site_lines(): "ends on" for an event whose end is still to come.
  - rule_push_duplicates(): the duplicates that came less than 5 s after a retried conflict (facts["push_after_conflict"]).
  - rule_bans(): "... and N more" after five addresses banned during the window.
  - timeline(): the Odoo lines of the service journal (details["service"]["odoo_events"]).
- Bugs fixed:
  - Symptom (PROD): "terminé le 2026-11-21" on 2026-11-09. Diagnosis: no check of the date. Fix: future end -> "se termine le".
  - Symptom: the advice of the memory risk (764 MB on PROD, 70 % of the memory over workers + cron) differed from step 6 of nginx-hardening.sh. Diagnosis: two rules. Fix: one rule in both programs (768 MB on PROD, 2048 MB on DEV).
- Safeguards and edge cases: without other_mb the reserve is 15 %; a limit under 256 MB is never advised.
- Checks performed: test_advisor (61 tests, class Version18 added) [OK]; catalogue complete and without stale entries.
- Action required: none.

### 1.7.20261109.081127 - Analysis of the night report: push duplicates, interruption over, memory risk, loops, failed e-mails one by one

- Title: the analysis says what really happened and gives a solution track for each failed e-mail.
- Reason: review on 2026-11-09 of the analysis of the night with the administrator (see app-log-live.py 1.178).
- Changes (apps/_advisor.py, lang/_advisor.fr.po, nginx-tools-tests/test_advisor.py):
  - KNOWN_MESSAGES: the push subscription already registered (mail_push_device, "endpoint must be unique") has its own cause; "could not serialize access" stays a retried conflict; any other "bad query" is now "to look at" (the reason is on the next line of the log).
  - New rule_push_duplicates() (information, cause confirmed).
  - rule_nginx_upstream(): number of refusals over the length of the interruption, requests answered 502, 503 or 504 during that time, reason of the stop in the service journal (KILLED_RE: oom-kill, status=9/KILL, Failed with result...), interruption over for more than RESOLVED_AFTER = 3600 s with Odoo running again -> information "(over)"; events before the first request read are said.
  - New rule_memory(): (workers + cron) x limit_memory_hard against the memory of the server or of its container, processes killed for lack of memory (memory.events), kernel messages; advice with the values to set.
  - New rule_hot_pairs(): one address asking the same page again and again (back-office call with a valid session, refused session, known person, or a public page).
  - rule_mails(): each failed e-mail with date and time, subject, recipients and full reason; SMTP_HINTS rewritten as (pattern, solution track) with ten tracks (authentication, sender refused, address that does not exist, mailbox full, temporary refusal, order of the commands, TLS, server unreachable, invalid address, refusal of the recipient server); generic reason only -> where to find the SMTP answer; two active outgoing servers on the same host and port reported; GENERIC_MAIL_REASON_RE.
  - rule_slow(): the detail of the five slowest requests (time, duration, address, SQL and Python time, action of the model for call_button/call_kw), slow requests on different pages less than SIMULTANEOUS_S = 60 s apart (cause: PostgreSQL busy or held by a lock, with the advice log_lock_waits), scheduled actions run around then.
  - rule_bans(): line on the score of nginx-log-audit.sh; new finding "Addresses banned by fail2ban during the window".
  - rule_account_forms(): known addresses from facts["known_ips"]; requests not found in the access logs read; portal accounts created with their date and sign-ins; several accounts that never signed in with a free sign-up -> to look at.
  - rule_odoo_errors(): the raw example of the grouped message.
  - Analyzer.add(confirmed=...) and render(): "Cause (confirmed)" when the cause is proven by what was read.
  - New timeline() for app-log-live.py --export-ai; new _span().
- Bugs fixed:
  - Symptom: "Odoo ERROR: bad query ... mail_push_device - Cause probable : mise à jour simultanée réessayée par Odoo". Diagnosis: one pattern grouped every "bad query" with the serialization conflicts. Fix: one pattern per cause.
  - Symptom: "[FAIL] Odoo injoignable depuis nginx : 33 fois" two days after the end of the interruption, "0 réglés". Diagnosis: no notion of an interruption over. Fix: RESOLVED_AFTER.
  - Symptom: "Formulaires ... 18 sur 18" with hosting providers counted as known people. Diagnosis: a resolved DNS name was taken for a person. Fix: known_ips.
  - Symptom: "Cause : Échec d'envoi de l'e-mail x2", nothing else. Diagnosis: only the first line of failure_reason was read, often the generic sentence. Fix: the full reason of each e-mail.
- Safeguards and edge cases: an interruption over but whose stop was a kill stays "to look at"; no memory finding with workers=0 (one process) or a worst case under 80 % of the memory; a loop on a public page of a known address is an information; hints are not repeated; the timeline keeps the 60 most recent events of the window.
- Checks performed: test_advisor (56 tests, of which Version17 and Pays) [OK]; catalogue complete and without stale entries.
- Action required: none.

### 1.6.20261106.110050 - Analysis: tests of this server, robot names, 404 of nginx, known people

- Title: six findings of the report of one day corrected so that the analysis tells the truth.
- Reason: review on 2026-11-06 of the report of one day (app-log-live.py --advise --days 1) of the administrator.
- Changes (apps/_advisor.py, lang/_advisor.fr.po, nginx-tools-tests/test_advisor.py):
  - rule_5xx: when every requester is an address of this server (loopback, facts["server_ips"]), the finding is an information ("made by this server itself: a test, a probe or a curl") and the exception is remembered; rule_odoo_errors: the Odoo ERROR with the same exception, and no visitor with it, is an information too.
  - server_name(): "this server" translated (it stayed in English), a loopback address is named "this server" instead of the first program seen on it.
  - ROBOT_NAME_RE: the robots are named by their token (Google-Read-Aloud, WhatsApp/2.23.20.0) and not by the first 60 characters of the User-Agent.
  - rule_repeated_4xx: a 404 whose page is the small one of nginx (about 150 bytes) and that the site itself links to: cause "nginx refuses an address that the site offers" and advice nginx-hardening.sh --update, instead of "correct the link".
  - registration_success(): when every registration has a visitor, the cause says that Odoo does not recognise this visitor on the second opening; the duplicates are "to check" and no longer "probably tried again".
  - rule_account_forms(): when half of the requests come from addresses that have an account (they have a name), the finding is an information "mostly from people already known" and no longer "a robot that creates accounts".
- Bugs fixed:
  - Symptom: "HTTP 5xx on registration/success: 6, problem" and "Odoo ERROR TypeError". Diagnosis: all of them were the tests of the administrator (probes of the analysis before 1.171, curl from the server); the requesters were shown as app-health-check.py and "this server". Fix: see above.
  - Symptom: "Qinghe Sun x9, cecchino x8" described as a robot creating accounts. Diagnosis: the rule counted the requests, not who makes them. Fix: known people.
- Safeguards and edge cases: an exception that visitors also cause stays a problem (a 5xx from an external address is never downgraded); the nginx origin needs the sizes of the 4xx answers read in the access log; without them the previous advice is kept.
- Checks performed: test_advisor (44 tests), test_i18n (only the failures already present on main).
- Action required: none. On the server: sudo nginx-hardening.sh --update (2.81) for the /event/page/N 404 shown by the report.

### 1.5.20261106.094106 - Who asked, who answered, retries, registrations of the confirmation links

- Title: the 404 findings show the origin of the answer and the kind of visitors; new finding for the confirmation page of an event registration.
- Reason: request of the administrator on 2026-11-06 (see app-log-live.py 1.172).
- Changes: nginx_details() (robots, browsers, queries, sizes), origin_lines(), registration_success(), REGISTRATION_SUCCESS_RE, ROBOT_AGENT_RE, BYTES_RE; French sentences in lang/_advisor.fr.po.
- Bugs fixed: none.
- Safeguards and edge cases: the classification of the robots is by the User-Agent only (a robot that pretends to be a browser counts as a browser); the median size of the 4xx answers decides between nginx (400 bytes or less) and Odoo.
- Checks performed: test_advisor (41 tests).
- Action required: none.

### 1.4.20261106.083524 - sitemap.xml 403 information, websocket not slow, limit_time_real wording

- Title: three false alarms of the analysis corrected.
- Reason: review on 2026-11-06 of the analysis of the night of the administrator.
- Changes:
  - apps/_advisor.py: the 403 of sitemap.xml are judged on the refused codes only (the 200 answers of the visitors and of the program no longer turn it into "sitemap.xml answers 403"); slow requests on /websocket and /longpolling ignored (LONG_CONNECTION_RE); a slowest request longer than limit_time_real says "more than" instead of "close to".
  - lang/_advisor.fr.po: new sentence. nginx-tools-tests/test_advisor.py: two tests.
- Bugs fixed: the three false alarms above (ClaudeBot refused by bot_blocker.conf made the point "sitemap.xml answers 403" to look at; a websocket of 4911 s was a "slow request close to limit_time_real=600 s").
- Safeguards and edge cases: a 404 or a 5xx on sitemap.xml still gives "to look at"; a real request beyond limit_time_real is still reported.
- Checks performed: test_advisor (39 tests).
- Action required: none.

### 1.3.20261105.071311 - Rules checked against a real analysis, details gathered, proposed corrections

- Title: the rules use the details read by app-log-live.py (odoo.conf, database, service journal, answer of the site) and each finding may carry a correction (fix) for --apply.
- Reason: request of the administrator on 2026-11-05 (app-log-live.py 1.167): output checked, advice verified by the program itself, corrections on request.
- Changes:
  - HOST_RE reads host="..." without its quotes; _bare_host() and internal_referers(detail, site_hosts): the site with or without www, on any port; nginx_details() counts the methods (GET, POST).
  - New exception_counts() (the exception of every occurrence of a message), trace_near() (the traceback logged within a few seconds of a time, UTC header of Odoo), first_error_trace(), odoo_settings_advice() (workers=0, too many workers for (2 x CPU) + 1, memory, slowest request close to limit_time_real).
  - New rule rule_nginx_upstream (nginx could not reach Odoo, linked to the starts and stops of the service; the other nginx messages as information); rule_5xx grouped by page, with addresses, traceback, scanner recognized (FUZZ_RE), forms; rule_sitemap_404 and rule_repeated_4xx: 404 counted by nginx, query strings grouped, redirects apart, answer of the site now, record in Odoo (event, product, page, similar page), redirect already defined, WordPress sitemap names (WP_SITEMAP_RE); rule_odoo_errors: nginx lines left out, known messages grouped (versions of the .map), cause drawn from the exception only when it is the usual one, VAPID key (TRACEBACK_HINTS); rule_mails: the database decides (failures, waiting queue, causes, servers); rule_slow: outside-SQL time explained, busiest hours, starts of Odoo, odoo.conf; rule_account_forms: POST and GET, sign-up setting, new portal accounts.
  - Findings carry fix = ("ban", addresses), ("mail", days) or ("warmup", None); render(apply_hint) prints it.
  - lang/_advisor.fr.po: new entries, stale ones removed.
- Bugs fixed: see app-log-live.py 1.167 (quoted host, 404 counts, 5xx not grouped, cause drawn from the last occurrence, nginx lines taken for Odoo errors).
- Safeguards and edge cases: every detail is optional (an absent one changes nothing); no single-word translation entry (they would translate URLs); placeholders never named like a word of the catalogues.
- Checks performed: test_advisor (37 tests).
- Action required from the user: none.

### 1.2.20261104.183145 - Rotated nginx logs compressed with gzip are read

- Title: read_tail() reads the rotated logs compressed with gzip (.gz).
- Reason: app-log-live.py 1.165 --advise reads the nginx access logs of a window of several weeks, most of them rotated and compressed.
- Changes: read_tail(): a .gz file is decompressed and the end of its text kept (same limit); nginx_details() therefore accepts .gz files.
- Bugs fixed: none.
- Safeguards and edge cases: a damaged .gz file gives no line, never an error.
- Checks performed: test_advisor (test_journal_compresse_gz).
- Action required from the user: none.

### 1.1.20261104.162540 - Advice of the two-letter false alarm updated for app-log-live.py 1.164

- Title: the advice of the false alarm "404 counted as a sitemap page" no longer asks for a fix of the program.
- Reason: app-log-live.py 1.164 takes only the codes of ISO 639-1 for language prefixes; the false alarm can now only come from a real language code that the site does not offer.
- Changes: rule_sitemap_404(): new text of the advice; lang/_advisor.fr.po: entry replaced.
- Bugs fixed: none.
- Safeguards and edge cases: the rule still recognizes a two-letter path, so older versions of app-log-live.py are still explained.
- Checks performed: test_advisor (catalogue test included).
- Action required from the user: none.

### 1.0.20261104.135312 - First version: analysis of the problems raised by app-log-live.py

- Title: shared module that turns the counters of the dashboard of app-log-live.py into findings with causes and recommended solutions, and keeps a history of the analyses.
- Reason: request of the administrator on 2026-11-04 (z key of app-log-live.py 1.163): analyze the problems raised, look at the detail of the logs and recommend solutions, with continuous improvement.
- Changes:
  - read_tail(), odoo_trace(), parse_traceback() (exception, message, module of the last frame in an addons folder, rlq-addons included), nginx_details() and internal_referers(): details read in the logs.
  - Analyzer and analyze(): rules for the 5xx errors, the 404 of sitemap.xml (false alarm of a two-letter path, truncated link, page gone), the repeated 404 outside the sitemap (dead internal link, unpublished product or event), sitemap.xml refused or missing, the Odoo messages (KNOWN_MESSAGES) and the exceptions of their tracebacks (TRACEBACK_HINTS), the concurrent update failures, the failed e-mails (SMTP_HINTS), the slow requests (SQL, Python, cold cache), the addresses to ban and those held back, the account forms, the latency sample. Severity: problem, to look at, information.
  - History: advisor-history.json, new occurrences per analysis (difference with the previous analysis of the same session), tags new, recurring, back, quiet; resolved problems; problems seen most often.
  - render(): summary, comparison with the previous analysis, findings with evidence, probable cause and recommendations.
  - lang/_advisor.fr.po: French translation (Source-Language: en).
- Bugs fixed: none (new module).
- Safeguards and edge cases: Python 3.8; every text through the translator given by the program, every piece of log data protected from translation; unreadable or corrupt history: started again empty, reason kept; history limited to 200 analyses and 90 days; one failing rule never stops the others.
- Checks performed: nginx-tools-tests/test_advisor.py.
- Action required from the user: none.

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

### 1.11.20261103.112517 - THEME is a common key of app-default.conf

- Title: THEME is a common key of app-default.conf.
- Reason: request of the administrator on 2026-11-03: a --theme N option for all the programs (dark background, light background, etc.), making sure that every color reads on the chosen background. Delivered first for app-log-live.py, web-monitor.py and nginx-log-audit.sh; the other programs follow on request.
- Changes:
  - CLES_COMMUNES gets THEME (apps/_i18n.sh reads it for the bash programs): one value for all the programs.
- Bugs fixed: none.
- Safeguards and edge cases: a program without --theme ignores the key as before; the program's own file wins over the common file.
- Checks performed: test_theme.py (the key is common in both readers), test_conventions.
- Action required from the user: none. To use a theme everywhere: THEME=2 in /etc/default/app-default.conf (or ~/.app-default.conf), or --theme N on one run; python3 apps/_theme.py --demo shows the themes.

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

## apps/_countries.py

### 1.0.20261109.081127 - Full names of the countries

- Title: new shared module: full name of a country from its two-letter code, in French and in English.
- Reason: request of the administrator on 2026-11-09: "Dans l'analyse et le sommaire, peux-tu rajouter le nom du pays au complet comme CD".
- Changes: apps/_countries.py (NAMES: 252 codes, ISO 3166-1 plus XK, EU, AP; name(), label()); used by app-log-live.py 1.178 (country_label()).
- Bugs fixed: none.
- Safeguards and edge cases: built-in table, no network and no extra package; names from CLDR, made longer where the short form is ambiguous (CD, CG); unknown code -> the code alone; empty code -> "".
- Checks performed: nginx-tools-tests/test_advisor.py, class Pays [OK].
- Action required: none.

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

## apps/_odoo_conf_check.py

### 1.2.20261109.222500 - Old key names read by Odoo are not unknown keys

- Title: xmlrpc_port, xmlrpc_interface and xmlrpc are reported as old names read by Odoo, not as unknown keys.
- Reason: report of the administrator on 2026-11-09 (DEV, nginx-hardening.sh 2.91 --update): « [FAIL] nginx -t refuse la configuration générique » followed by « syntax is ok / test is successful », and « odoo.conf (ligne 41 xmlrpc_port) : clé inconnue d'Odoo ».
- Changes: new constant OUTDATED (xmlrpc_port -> http_port, xmlrpc_interface -> http_interface, xmlrpc -> http_enable, as odoo/tools/config.py load()); check(): these keys -> "info" « old name, read by Odoo as ... »; nginx-tools-tests/test_odoo_conf_check.py.
- Bugs fixed: symptom: « clé inconnue d'Odoo, ignorée sans message (faute de frappe ?) » for xmlrpc_port; diagnosis: Odoo 18 renames these keys when it reads the file, so they are not in its list of options; fix: said as an old name.
- Safeguards and edge cases: the other unknown keys are still warnings.
- Checks performed: test_odoo_conf_check [OK].
- Action required: none.

### 1.1.20261109.213000 - Python of the virtual environment of Odoo, import failure is not an error of the file, empty TSV fields

- Title: the check by Odoo itself uses the Python of Odoo's virtual environment; when it cannot load Odoo it says so instead of failing the file.
- Reason: report of the administrator on 2026-11-09 (DEV, nginx-hardening.sh --update): step 8 said « [FAIL] odoo.conf (ligne 0 Odoo refuse ce fichier : ModuleNotFoundError: No module named 'babel') : ».
- Changes: new function _python_of() (argv[0] when it is a path, otherwise argv[0] in the PATH of the process from /proc/PID/environ, then VIRTUAL_ENV, then /proc/PID/exe); find_odoo() uses it; check(): ModuleNotFoundError or ImportError -> "info" (check by Odoo not done, give --python); --tsv writes "-" for an empty line number or key.
- Bugs fixed:
  - symptom: « Odoo refuse ce fichier : ModuleNotFoundError: No module named 'babel' »; diagnosis: /proc/PID/exe resolves the symlink of the venv to /usr/bin/python3.x, whose site-packages lack Odoo's packages; fix: the Python of the PATH of the process (its venv).
  - symptom: « (ligne 0 Odoo refuse ce fichier : ...) : » with the message in the place of the key; diagnosis: read with IFS=tab merges the empty fields; fix: "-" in the empty fields.
- Safeguards and edge cases: a Python that cannot load Odoo never makes an error of the file; a real refusal of Odoo (bad value) stays an error.
- Checks performed: test_odoo_conf_check (7 tests: test_11_python_sans_odoo_et_champs_vides, test_11_python_de_l_environnement_virtuel) [OK].
- Action required: none.

### 1.0.20261109.211500 - New: odoo.conf checked the way Odoo 18 reads it

- Title: new shared module and command that check an Odoo configuration file without starting Odoo.
- Reason: request of the administrator on 2026-11-09: Odoo refused "limit_memory_soft_gevent = 2147483648 # (2048 Mo" (comment after the value); is there a program that checks the configuration of Odoo, or can one be written.
- Changes: new file apps/_odoo_conf_check.py: check(path, odoo_bin, python, language, use_odoo) and the command "python3 apps/_odoo_conf_check.py [--lang fr|en] [--odoo-bin PATH] [--python PATH] [--tsv] FILE" (exit 0 no error, 1 errors, 2 unreadable). Checks: comment after a value, key twice, line outside a section, no [options], integer and decimal options of Odoo 18, values in bytes that look like MB, limit_memory_soft above limit_memory_hard or under 1024 MB, gevent limits not set; with the Odoo of the server (found in the running processes, or --odoo-bin and --python): config.parse_config of Odoo itself and the keys Odoo does not know; messages in French and English; nginx-tools-tests/test_odoo_conf_check.py.
- Bugs fixed: symptom: Odoo did not start after "limit_memory_soft_gevent = 2147483648 # (2048 Mo" was added; diagnosis: Odoo reads its file with configparser.RawConfigParser without inline comments, so the comment stays in the value and the integer cast refuses it; our own readers (apps/_odoo_conf.py) cut at "#" and said nothing; fix: the new check reports a comment after a value as an error, with the line to write.
- Safeguards and edge cases: reads only; the parsing by Odoo runs with "python -I" from /, 120 s at most; without root the processes of the odoo account cannot be read: the check by Odoo itself is then skipped and said so.
- Checks performed: test_odoo_conf_check (real case of 2026-11-09, key twice, type, units, memory, fake Odoo package for the parsing and the unknown keys, finding of the analysis, step 8) [OK].
- Action required: none.

## apps/_i18n.py

### 1.24.20261109.190000 - Own line editor of the answers: ^H and ^? erase (also apps/_i18n.sh, apps/_menu.py)

- Title: every question of the Python programs (saisie(), used by all of them) and the Ctrl+C question of the Bash programs erase with ^H AND ^?.
- Reason: report of the administrator on 2026-11-09: "^H" still shown when a program asks a question.
- Changes:
  - apps/_i18n.py: _lire_reponse_terminal() puts the terminal without ICANON nor ECHO (ISIG kept, VMIN 1) for the answer; new editer_ligne() (echo, ^H and ^? erase one character, ^U the line, ^W the last word, Enter ends, ^D on an empty line = end of file, arrows ignored, UTF-8 and wide characters), appliquer_effacements(), EFFACEMENTS; saisie() without a terminal applies the erase characters.
  - apps/_i18n.sh: appliquer_effacements TEXT and lire_ligne_editee VARIABLE (Bash editor); _ctrl_c_demande reads its answer with lire_ligne_editee.
  - apps/_menu.py: _saisie() calls saisie() of apps/_i18n.py (builtin input() with the erase characters applied if the module is missing).
  - nginx-tools-tests/test_saisie_terminal.py: tests in a real pseudo-terminal set with stty erase ^? (Python saisie, question_reponse of odoo-update-module.sh, lire_ligne_editee, appliquer_effacements); every Bash question must use read -e; the old checks of the termios flags and the frozen versions removed.
- Bugs fixed: symptom: in a question, the erase key showed "3^H^H" and the answer kept the ^H characters; diagnosis: the kernel line mode (stty icanon echoe, put back by tty_ligne) knows ONE erase key only (stty erase, usually ^?), while some terminals (PuTTY, some ssh clients) send ^H; ECHOE does not help when the key is not the erase key; fix: the answers are edited by readline (read -e) or by our own line editor, where ^H AND ^? erase.
- Safeguards and edge cases: Ctrl+C keeps its question during an answer (os.read is resumed after the handler, which reads its own answer with the same editor and puts the terminal back); the terminal is always put back in its previous state (finally); without termios: plain readline() with the erase characters applied.
- Checks performed: test_saisie_terminal, test_saisie, test_ctrl_c [OK].
- Action required: none.

### 1.23.20261102.225620 - Ctrl-C during a question: no more "reentrant call" traceback (Python 3.13)

- Title: the answer to "Interrompre le programme ? [o/N]" is read directly on the descriptor of the terminal, so a Ctrl-C pressed while a program waits for an answer no longer ends with a Python traceback.
- Reason: request of the administrator on 2026-11-02: in web-monitor.py, Ctrl-C at "Appuyez sur Entrée pour ouvrir le rapport complet dans less (q pour quitter), ou Ctrl-C pour terminer" printed the question, then "RuntimeError: reentrant call inside <_io.BufferedReader name='<stdin>'>". Every Python and bash program must stop cleanly on Ctrl-C.
- Changes: new function _lire_ligne_descripteur(fd) (os.read until the end of the line, decoded with the encoding of stdin); _lire_reponse_terminal() uses it when the terminal has a descriptor (sys.stdin.readline() otherwise, as before).
- Bugs fixed:
  - Symptom: traceback "RuntimeError: reentrant call inside <_io.BufferedReader name='<stdin>'>" after Ctrl-C during any question of a Python program (saisie(), ctx.input(), web-monitor.py offer_less).
  - Diagnosis: the program waits in sys.stdin.readline(); Ctrl-C runs the handler of installer_confirmation_ctrl_c, which read its answer with sys.stdin.readline() too. Python 3.13 refuses a second read on the same buffered object while the first one is in progress. The test test_python_ctrl_c_pendant_une_question_sans_trace failed on main with Python 3.13 for this reason.
  - Fix: os.read on the descriptor: no buffer and no lock; the handler reads its answer, then the interrupted read resumes (or KeyboardInterrupt stops the program when the answer is yes).
- Safeguards and edge cases: line mode, echo and erase key are still set during the answer and restored afterwards; end of file still means yes; a read interrupted by a signal is retried; without a terminal descriptor, the previous reading is kept. A second Ctrl-C during the question still confirms. Bash programs are not affected (apps/_i18n.sh unchanged; their Ctrl-C tests pass).
- Checks performed: nginx-tools-tests/test_ctrl_c.py: 17 tests [OK], including test_python_ctrl_c_pendant_une_question_sans_trace (no, then the question is answered; yes, clean stop; English), which failed before this change.
- Action required: none.

### 1.22.20261101.231500 - Retour arrière : écho et effacement rétablis avant chaque réponse

- Title: a new function saisie(invite) reads the answer in line mode with echo and erase (ECHOE), then restores the terminal. The context's input() (I18N.input) uses it, so every program that prints its questions through the translator gets the fix.
- Reason: Request of the administrator: in nginx-hardening.sh, at the prompt "Faire le setup du courriel (relais SMTP) maintenant ? [o/N] :", the Backspace key shows "d^H^H^H^H" and erases nothing. The same problem can hit every program that asks a question, so every interactive prompt of the Bash and Python programs must be checked and fixed.
- Changes: saisie() in apps/_i18n.py (uses _lire_reponse_terminal(), EOFError at end of file, input() without a terminal); the context's _input is saisie. apps/_i18n.sh: new function tty_ligne() (stty icanon echo echoe icrnl on /dev/tty, nothing without a terminal).
- Bugs fixed: symptom: "d^H^H^H^H" on screen when erasing, the characters are gone from the answer but not from the screen. Diagnosis: ECHOE off with ICANON on (see the explanation above). Fix: the terminal is set again before each answer.
- Safeguards and edge cases: Without a terminal (pipe, cron, stdin not a tty): nothing is changed, the programs behave as before. Stdin and /dev/tty redirections are guarded with || true (set -e). Password prompts (read -s) are not changed. The helper is defined in apps/_i18n.sh; a program without that file gets a no-op fallback.
- Checks performed: nginx-tools-tests/test_saisie_terminal.py (new, static): every interactive read -p / read -e of the Bash programs has tty_ligne on its line; tty_ligne is defined and sets icanon echo echoe; saisie() is defined and used by the i18n context; apps/_menu.py has its own line reader; versions.
- Action required from the user: none.

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

### 1.8.20261104.204925 - Parsed addresses kept in the list lookups

- Title: _plus_specifique() parses each address once.
- Reason: app-log-live.py 1.166 --advise looked up the same addresses hundreds of thousands of times in the whitelist and the places file.
- Changes: new _adresse() (functools.lru_cache, 8192 addresses) used by _plus_specifique().
- Bugs fixed: none (speed).
- Safeguards and edge cases: the parsed address is immutable, the entries are still read at each call (a reloaded list is seen at once); an invalid address is not cached and still gives None.
- Checks performed: test_listes, app-log-live tests.
- Action required from the user: none.

### 1.7.20261102.104500 - Dated [temporaire] entries

- Title: the readers of the white list read the option [temporaire AAAA-MM-JJ HH:MM:SS] and leave out expired or undated entries.
- Reason: see nginx-hardening.sh 2.76.
- Changes: Entree gains temporaire and expiration; DATE_RE; maintenant(); charger removes the expired ones and sets Listes.expirees. Bash: listes_lire reads the option as temporaire=DATE (or temporaire=invalide); listes_blanche applies the same rule; listes_maintenant; listes_temporaires.
- Bugs fixed: in listes_lire, the bash loop over the bracketed options was reading BASH_REMATCH after the date test had overwritten it, and never terminated. The match is now saved first.
- Safeguards and edge cases: same rule in both readers, checked by the tests at two dates; an invalid date is reported.
- Checks: nginx-tools-tests/test_listes.py.
- Action required: none.

### 1.6.20261102.102600 - DNS names are recognised, not read as addresses

- Title: the readers of the white list recognise DNS names and leave them to nginx-hardening.sh.
- Reason: see nginx-hardening.sh 2.75.
- Changes: est_nom_dns, noms_dns (Python); listes_nom_dns, listes_noms_dns (bash). A name is never reported as an invalid address and is never returned by the address functions.
- Bugs fixed: none.
- Safeguards and edge cases: an IPv4 or IPv6 address is never a name (a name needs a letter and a dot).
- Checks: nginx-tools-tests/test_dns_blanche.py, test_listes.
- Action required: none.

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

### 1.2.20261102.080324 - Time window instead of "stalled" streams: lines placed in time order

- Title: the merge holds each line APP_LOG_MERGE_WAIT seconds (1.5 by default) before releasing it, instead of declaring a silent stream stalled.
- Reason: the nginx and Odoo lines of the live display were out of order (see app-log-live.py 1.150).
- Changes:
  - Merger: the lines wait in a heap sorted by log time; a line is released when its log time is at least --wait seconds in the past (wall clock). The "stalled" state and the per-stream buffers are removed.
  - Start: nothing is released before every stream has delivered a line or ended (or --wait seconds have passed), so that the history of several files is merged in order.
  - End: when every stream has ended, what remains is released in order.
  - Merger.late counts the lines that arrive after a later line was released; they are printed in place, not dropped.
  - WAIT_DEFAULT: 2 -> 1.5 seconds (APP_LOG_MERGE_WAIT). Header comment updated.
  - Files touched: apps/_logs_merge.py, nginx-tools-tests/test_logs_merge.py.
- Bugs fixed:
  - Symptom: out-of-order lines in the merged stream when one source is quiet for more than 2 seconds.
  - Diagnosis: a stream silent for 2 seconds was marked "stalled" and no longer waited for; the lines of the other streams were released first, so a late line of the stalled stream came out after them.
  - Fix: the lines are held for a short window instead, in a heap sorted by log time.
- Safeguards and edge cases:
  - A silent stream does not hold back the others: each line is released after its window, whatever the other streams do.
  - Lines of the same second (nginx has only one-second precision) keep their arrival order.
  - A line without a time takes the time of the previous line of its stream (as before).
  - --no-follow: every line is released in time order once every stream has ended.
- Checks performed: py_compile; test_logs_merge: 13 tests OK (9 existing ones unchanged, 4 new ones: late line placed in order, silent stream does not hold back the others, start waits for the history of each file, end of every stream empties the queue).
- Action required from the user: none.

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

## apps/_vpn.py

### 1.1.20261102.230844 - The abuse mailbox of the block is read too

- Title: kind_of() also reads the abuse mailbox of the block; option --abuse of the command line.
- Reason: 132.196.59.85 (organisation "Divya Quamara", network "cloud", abuse@microsoft.com) was a rented server for the investigation but "aucun indice" for the type of address.
- Changes: kind_of(organisation, network, short, abuse); main(): --abuse.
- Bugs fixed: inconsistency described above.
- Safeguards and edge cases: web-monitor.py keeps calling kind_of without the mailbox (unchanged results there).
- Checks performed: test_279_sondes_refusees_comptent_dans_l_enquete [OK].
- Action required: none.

### 1.0.20261102.224544 - New module: VPN, Tor, relay or hosting provider behind an address

- Title: shared module that guesses what hides behind an address from the owner of its block (VPN, Tor, relay, hosting provider), checks the official list of Tor exits, and gives the owner's name to show.
- Reason: request of the administrator on 2026-11-02 (improvements 1, 2 and 3 after the investigation of 45.138.12.41).
- Changes: VPN_OWNERS, VPN_OWNERS_RE, VPN_PRIORITY (moved from web-monitor.py 2.85, unchanged); kind_of(organisation, network, short); owner_label() and first_word() (network name when the organisation is generic: GENERIC_ORG_RE); tor_exits() with a cache of one day; command line "_vpn.py IP --org ORG --net NET [--no-tor] [--verbose] [--version]" printing KIND, NAME, TOR, TOR_LIST_DATE, LABEL separated by ASCII 31.
- Bugs fixed: none.
- Safeguards and edge cases: never an exception; failed download keeps the cache; a list of fewer than 10 addresses never replaces it.
- Checks performed: test_278_vpn_module_partage [OK].
- Action required: none.

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
