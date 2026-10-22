# Testing, translation and contributing

## The test suite

`nginx-tools-tests/run-all.sh` validates the whole suite: file presence, syntax (`bash -n`, `py_compile`), **ShellCheck**, **ruff**, the unit/integration tests under each awk (mawk, gawk, busybox if present) **limited to the server's environment** (modules tagged `commun` + `odoo` or `bbb`; `--all-environments` runs all, `--list` shows without running), the deployed nginx configuration compared with the reference copy (Odoo), then read-only checks of the real server (outside the verdict). A failing test is rerun alone: confirmed failure (blocking) or `[UNSTABLE]`.

```bash
nginx-tools-tests/run-all.sh                   # everything for this server
python3 -m unittest test_i18n test_anonymiser  # targeted run from the tests folder
```

Rules the suite enforces: every long option appears in `doc/NAME.conf.example`; options are listed alphabetically; every `test_*.py` declares `ENVIRONMENT = "commun" | "odoo" | "bbb"`; the first output line is `NAME vVERSION`; no Python newer than 3.8 syntax; no leftover temporary directory; **no real configuration file is modified** (sentinels watch `/etc/default` and `~`); tests redirect every system path to a temporary folder and simulate `ufw`, `iptables`, `nginx`, `systemctl`.

Do not run an old test suite against new programs (or the reverse): deploy both archives together.

## Pitfalls that cost a cycle before

* `systemctl is-active` prints the state *and* returns non-zero: do not write `$(... || echo unknown)`.
* ShellCheck's development version is newer than Debian's and does not flag `A && B || C` (SC2015): a test looks for that pattern itself. Never put an apostrophe in `${x:+...}` inside double quotes.
* A test that loads a program inside the test process reads the real `os.environ` and `/proc`; fix machine dependencies at process level (`helpers.py`).
* Documentation-range addresses (`192.0.2.x`, `198.51.100.x`, `203.0.113.x`) count as private for Python's `ipaddress`: use other public addresses in tests.
* Cutting by bytes (`cut -c`) splits accented characters: cut with Python.
* Python prompts load `readline`; bash prompts use `read -e`.

## Translation

Programs print in English or French. The mechanism is a *post-translation of the output*: `apps/_i18n.py` (Python) and `apps/_i18n.sh` + `apps/_traduire.py` (bash) replace known fragments with the text of `lang/NAME.XX.po` (standard PO format; see `lang/README.md`). Shared catalogs `_config` and `_i18n` are always loaded. `test_i18n` scans every string literal and fails if a message has no catalog entry. Programs already migrated to English source (`zip-versions.py` first; the rest follow stage by stage) declare `"Source-Language: en\n"` in `lang/NAME.fr.po`: the `msgid` are then the English texts of the code and the `msgstr` the French translation. To add a language, copy a `.po` file, translate the `msgstr` lines, run the tests.

## Reporting a problem

Run the failing program with `--report-err` (add `--anonymize` before posting) and attach the report.
