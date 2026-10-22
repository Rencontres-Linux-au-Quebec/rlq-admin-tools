# app-log-check.py - analysis of Odoo's journal

Reads the systemd journal of the Odoo service (auto-detected among `erplibre.service`, `erplibre_erplibre.service`; or `--service`; `--namespace` if the unit uses `LogNamespace=`) and sorts what it finds into numbered sections: protocol attacks, Python tracebacks grouped by signature [2], other errors [3], known noise, diagnostics [5], undelivered e-mails.

By default it analyses what is new since the last run; `--init` takes the whole available history; `--last HOURS` restricts the window.

```bash
app-log-check.py                        # new since the last run
app-log-check.py --errors-only --full-trace
app-log-check.py --by-hour --days 7 --top 15   # problems by hour and by day; does not use or move the saved position
```

## Reading `--by-hour`

It reports errors, error pages and "Session expired" with their peaks. A flood of thousands of "Session expired" lines usually comes from **one tab left open**, not from a server fault: the report says whether one client or several are involved and whether peaks match restarts. Two addresses for one account mean one account on two devices, not "several clients"; Odoo CE allows several simultaneous sessions per account - if a login on one device invalidates another, look for a module.

## Undelivered e-mails

Typical causes diagnosed (read-only; Odoo is never modified): 452 "Maximum number of messages per session" (lower `mail.session.batch.size`), 503 "Multiple MAIL commands" (cascade of the 452), sender rejected (outgoing server with a *From filter*, `mail.default.from`, `mail.catchall.domain`). Use `odoo-mail-retry.py` to resend.

## Options
{{HELP}}
