# NEU-1535 — Set Reply-To on outgoing email

**Ticket:** [NEU-1535](https://linear.app/neuroticsasquatch/issue/NEU-1535/set-reply_to-for-resend-emails)
**Project:** Boone Gifts: Maintenance
**Repo:** boone-gifts-backend
**Branch:** `tom/neu-1535-set-reply_to-for-resend-emails`

## Why

Production mail goes out through Resend's SMTP relay with `From: Boone Gifts <noreply@boone.gift>`.
That mailbox does not receive mail, so anyone who hits reply on an invite, a password reset, a
connection request or a list-shared notification gets a bounce. We want replies to land somewhere
a person reads, without changing the visible sender.

## What to build

Add one setting, `APP_EMAIL_REPLY_TO`, and have the SMTP sender stamp it on every message as a
`Reply-To` header. Nothing else about the message changes.

### Setting

- `app/config.py`: `email_reply_to: str = ""`, placed next to `email_from`.
- Free-form string in the same shape as `email_from`: a bare address or
  `Display Name <address>`. Passed through as-is; no parsing or validation.
- Default is the empty string.

### Sender behaviour (`app/email/sender.py`)

- `_send_via_smtp`: after setting `From`, if `settings.email_reply_to` is non-empty, set
  `msg["Reply-To"] = settings.email_reply_to`. If empty, do not add the header at all. The
  message must be byte-for-byte what it is today when the setting is unset.
- `_send_via_log`: unchanged. The log provider does not print the reply-to.
- `send_email`'s signature is unchanged. All five call sites (password reset, admin invite, family
  invite, connection request, list shared) pick the header up automatically. No call site changes.

### Documentation and environment

- `.env.example`: add `APP_EMAIL_REPLY_TO=` under the Email block with a one-line comment that
  it is the address replies go to, and that leaving it empty omits the header.
- `docs/runbook.md`: add a row for `APP_EMAIL_REPLY_TO` to the production environment variables
  table, noting it must be set in Coolify to a mailbox that receives mail.
- `AGENTS.md`: add `APP_EMAIL_REPLY_TO` to the environment variables table.

The production address itself is a deploy-time value configured in Coolify. It is deliberately
not recorded in the repo or in this spec.

## Acceptance criteria

1. With `APP_EMAIL_PROVIDER=smtp` and `APP_EMAIL_REPLY_TO=Boone Gifts <hello@test.com>`, the
   message handed to `smtplib.SMTP.send_message` has `msg["Reply-To"] == "Boone Gifts <hello@test.com>"`,
   and `From`, `To` and `Subject` are unchanged from today.
2. With `APP_EMAIL_REPLY_TO` empty, the message has no `Reply-To` header (`msg["Reply-To"] is None`).
3. The log provider's output is unchanged whether or not the setting is set.
4. The app starts normally with the setting absent from `.env`. There is no startup validation.
5. Existing email tests in `tests/unit/test_email.py` still pass unmodified.

## Tests

Extend `tests/unit/test_email.py`'s `TestSendEmailSmtpProvider`, using the existing
`_configure_smtp` helper (add `"email_reply_to": ""` to its defaults so the empty case is the
baseline for every existing test):

- `test_sets_reply_to_when_configured`: override `email_reply_to`, assert the header value.
- `test_omits_reply_to_when_empty`: default config, assert `msg["Reply-To"] is None`.

No integration tests. No migration.

## Key decisions

- **One global address, not per email type.** Every email replies to the same mailbox. A
  per-sender reply-to (for example an invite replying to the inviter) was considered and rejected
  as scope creep for a maintenance fix; it can be added later by giving `send_email` an optional
  `reply_to` parameter that defaults to the setting.
- **Empty means omitted, not an error.** The dev stack (Mailpit) and the log provider keep
  working with no `.env` changes. Production opts in by setting the variable. Startup validation
  like `APP_JWT_SECRET`'s was rejected because it would break every existing dev `.env`.
- **Value lives in deployment.** The address is not a code default and not in the repo.

## Out of scope

- Changing the `From` address or display name.
- Per-email or per-recipient reply-to.
- Validating that the reply-to address is well-formed or actually receives mail.
- Any change to the log provider or to the email templates.
- CONTEXT.md and ADRs: this touches no domain vocabulary and is trivially reversible.
