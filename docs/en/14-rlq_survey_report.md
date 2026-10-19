# rlq_survey_report — Odoo 18 module

Odoo 18 Community module (depends on `survey`, `mail`, `event`) for the monthly surveys of Rencontres Linux au Québec. Full end-user documentation (in French) is the *User guide* shipped in `doc/Guide-utilisateur-rlq_survey_report.html` and served inside Odoo at `/rlq_survey_report/aide`. This page is the administrator's view.

## Features

* **Reports** from native `survey.user_input` data: summary across meetings, per-meeting detail, per-participant sheet, “watch” section; exports HTML, PDF, Excel protected by a password (privacy law compliance), optional anonymization of participants; history of generated files.
* **Per-ticket survey**: each event ticket type can point to a different survey; a registration field holds the right survey link for e-mail templates.
* **Follow-up actions** and internal comments per survey.
* **Answers e-mailed to the participant** when a survey is completed (opt-in per survey).
* **Registration alerts**: e-mail when an event reaches N registrations, repeated every N (`rlq_alerte_repeter`), and on each completed survey.
* **Groups and tags of registrants**: one Odoo group per ticket (`RLQ-<PREFIX>-<ticket>`), groups bound to survey answers, mirrored as partner tags; periodic synchronization per survey and per event (every N minutes, minimum 5, event stops automatically one day after its end); a “Check groups and tags” wizard previews before applying.
* **Invalid e-mail addresses of registrations** (1.109): every registration is flagged *invalid* (cannot receive mail, e.g. `mariebc33@gmail'com`), *probable typo* (`gmial.com`) or *disposable*, with the suggested correction. A punctuation mistake that changes no letter is corrected at registration time (before the confirmation e-mail leaves). Menu *Events > Invalid e-mails*: the list, the button **Fix and resend** (registration and its contact fixed, failed e-mails re-addressed and queued again, confirmation sent again) and the failed outgoing e-mails (administrators).

## System parameters

| Key | Role |
|---|---|
| `rlq_survey_report.mot_de_passe_defaut` | default password pre-filled in the export form — **set it after installation** |
| `rlq_survey_report.courriel_inscriptions` | address(es) for registration alerts when the event has none |
| `rlq_survey_report.url_aide` | target of the “Help” button |
| `rlq_survey_report.etiquettes_groupes` | `1` (default) partner tags for groups; `0` disables |
| `rlq_survey_report.registration_email_autofix` | `syntax` (default: punctuation / spaces only), `off`, or `typos` (also a misspelled popular domain) |

## Scheduled actions

Daily purge of non-anonymized copies older than 3 days; daily tag synchronization; every 5 minutes the periodic survey/event synchronization.

## Update procedure

Use `odoo-update-module.sh --backup --zip rlq_survey_report.18.0.1.N.0.zip`. **Test on a development database first**: this module was written without an Odoo instance at hand; `doc/NOTES_VALIDATION.md` lists, version by version, what must be confirmed on a real instance, and Odoo tests (`tests/`) are provided but were not run by the author's tooling. Run them with:

```bash
odoo-bin -d TEST_DB -i rlq_survey_report --test-enable --test-tags rlq_survey_report --stop-after-init
```

The module's `run-all.sh` chains ruff, syntax checks, standalone tests (no Odoo needed) and, when PostgreSQL and Odoo exist, a disposable database with the Odoo tests.
