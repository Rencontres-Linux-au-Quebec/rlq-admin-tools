# odoo-mail-retry.py - list and resend failed e-mails

Reads PostgreSQL (root) and lists Odoo e-mails in **exception** state ("Delivery failed"): subject, date, recipients (masked unless `--details`) and a cause classified as *transient* or *PERMANENT*. Then a menu offers: `t` all, `l` a batch of the oldest N (`--batch`), `c` choose, `N` none.

```bash
odoo-mail-retry.py --db mydb --days 30
odoo-mail-retry.py --resend --yes --batch 10     # non-interactive, oldest 10
odoo-mail-retry.py --sent 20                     # latest 20 SENT e-mails
```

* "Resend" only puts the state back to *Outgoing* (like the "Retry" button); Odoo's scheduled action sends them.
* It is the **only program of the suite that writes to Odoo's database**, guarded by `state = 'exception'`, with confirmation, and every action is recorded in `/var/lib/nginx-tools/mail-retry.log`. Writing straight to SQL does not clear Odoo's parameter cache: do not use it to change settings.
* Schema note: `mail.mail` inherits `mail.message` (`_inherits`), so the **subject** is in `mail_message.subject`.
* Never resends without a terminal unless `--resend --yes`.

## Invalid addresses of registrations

Before the failed e-mails, the program lists the event registrations whose e-mail address is invalid or misspelled, with the suggested correction (`marie@hotmail'com` -> `marie@hotmail.com`, `hotmial.com` -> `hotmail.com`). The menu fixes them all (`a`), or one by one (`c`: Enter accepts the suggestion, or type another address, `s` skips); `--invalid-emails` shows only them, `--fix --yes` applies the suggestions without questions. A fix updates, in one transaction, the registration, its contact (only if it holds the same wrong address) and the failed e-mails of that registration, which go back to *Outgoing*. The login of an Odoo account is never changed. A failed e-mail addressed to an invalid address is shown with that cause: resent as is it would fail again.

## Options
{{HELP}}
