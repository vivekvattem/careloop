# Phase 5: notifications and medication reminders

CareLoop writes notification intent to a durable PostgreSQL outbox in the same transaction as appointment, prescription, or approval changes. API responses never wait for email delivery. The worker (`python -m app.cli.run_notification_worker --once`) claims due jobs with row locks and `SKIP LOCKED`, commits claims before provider calls, and records outcomes afterward.

The default `log` provider makes no network calls. Retryable failures use exponential backoff; permanent or exhausted failures remain auditable. Medication schedules have one record per stored reminder time, use `Asia/Kolkata` as the development fallback timezone, respect dates and inactive medication, and create idempotent reminder jobs. Templates are deterministic and never include private notes.

Evaluation talking points: transactional outbox, out-of-transaction email, idempotency, concurrent claiming and stale-claim recovery, deterministic timezone scheduling, retry classification, and fake/log test providers.

## Email providers

`CARELOOP_EMAIL_PROVIDER=log` remains the default and makes no network requests. The existing `sendgrid` provider remains available. Set `CARELOOP_EMAIL_PROVIDER=resend` to use Resend through the same outbox worker; it does not change notification schemas, job claiming, retry behavior, or CareLoop's database idempotency safeguard.

For local Resend testing, create a Resend account and API key, then add it only to the ignored `backend/.env` file. Resend's `onboarding@resend.dev` sender can send only to the account email in its testing mode. Verify a custom domain before sending to other recipients.

```env
CARELOOP_EMAIL_PROVIDER=resend
CARELOOP_RESEND_API_KEY=
CARELOOP_RESEND_BASE_URL=https://api.resend.com
CARELOOP_EMAIL_FROM_ADDRESS=CareLoop <onboarding@resend.dev>
CARELOOP_EMAIL_TIMEOUT_SECONDS=8
```

The Resend adapter calls `POST /emails` with only the deterministic template output, recipient, configured sender, subject, and the outbox idempotency key in Resend's `Idempotency-Key` header. It stores only Resend's safe message ID. It does not send LLM-generated text, symptoms, diagnoses, medical history, or private doctor notes. Medication reminders include only the stored medication fields and the instruction to follow the clinician's prescription.

Timeouts, connection failures, 429s, and 5xx responses use the existing retry path. Missing configuration plus 400, 401, and 403 responses are permanent. Raw response bodies and API keys are never stored in failure records or logged.

## Generic SMTP and local Mailpit

Set `CARELOOP_EMAIL_PROVIDER=smtp` for a generic SMTP server. The safe example configuration targets a local Mailpit-style listener and intentionally uses no credentials:

```env
CARELOOP_EMAIL_PROVIDER=smtp
CARELOOP_SMTP_HOST=localhost
CARELOOP_SMTP_PORT=1025
CARELOOP_SMTP_USERNAME=
CARELOOP_SMTP_PASSWORD=
CARELOOP_SMTP_USE_STARTTLS=false
CARELOOP_EMAIL_FROM_ADDRESS=notifications@careloop.app
CARELOOP_EMAIL_TIMEOUT_SECONDS=8
```

If STARTTLS is enabled, the provider negotiates STARTTLS before sending. SMTP authentication is attempted only when both username and password are supplied; providing only one is rejected as invalid configuration. Timeout, connection, and SMTP 4xx failures follow the existing retry path. Authentication, invalid sender/recipient, and SMTP 5xx failures are permanent. SMTP credentials are never included in exceptions, logs, or outbox failure fields.

The provider returns a short deterministic safe message identifier derived from the existing CareLoop idempotency key. Duplicate outbox processing remains guarded by the existing sent status and database idempotency key. For real SMTP, put credentials only in the ignored `backend/.env`; never commit them or place them in `.env.example`.
