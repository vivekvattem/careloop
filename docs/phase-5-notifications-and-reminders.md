# Phase 5: notifications and medication reminders

CareLoop writes notification intent to a durable PostgreSQL outbox in the same transaction as appointment, prescription, or approval changes. API responses never wait for email delivery. The worker (`python -m app.cli.run_notification_worker --once`) claims due jobs with row locks and `SKIP LOCKED`, commits claims before provider calls, and records outcomes afterward.

The default `log` provider makes no network calls. Retryable failures use exponential backoff; permanent or exhausted failures remain auditable. Medication schedules have one record per stored reminder time, use `Asia/Kolkata` as the development fallback timezone, respect dates and inactive medication, and create idempotent reminder jobs. Templates are deterministic and never include private notes.

Evaluation talking points: transactional outbox, out-of-transaction email, idempotency, concurrent claiming and stale-claim recovery, deterministic timezone scheduling, retry classification, and fake/log test providers.
