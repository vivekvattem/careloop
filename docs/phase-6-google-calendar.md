# Phase 6: Google Calendar synchronization

Phase 6 lets an authenticated patient connect a Google Calendar and queue calendar synchronization for their CareLoop appointments. It is an appointment integration, not Google sign-in: CareLoop continues to use its own authentication and authorization system.

## OAuth and token security

The patient dashboard asks the authenticated backend for an OAuth authorization URL and then navigates the browser to Google. The backend creates a cryptographically random OAuth state value, stores only its SHA-256 hash, expires it after ten minutes, and consumes it before exchanging the authorization code. A callback can therefore be used once; a failed exchange requires a fresh connect flow.

The callback redirects only to the local patient result route:

```text
http://localhost:5173/patient?calendar=connected
http://localhost:5173/patient?calendar=failed
```

Access and refresh tokens are encrypted with Fernet before database persistence. Tokens, authorization codes, client secrets, OAuth state, and raw Google errors are never returned in API responses, stored by the frontend, or written to worker output. The integration requests only `https://www.googleapis.com/auth/calendar.events`.

On expiry, the worker refreshes the access token and persists the encrypted replacement. A rotated refresh token is persisted only when Google sends one; otherwise the existing encrypted refresh token is retained. `invalid_grant`, 401/403 authorization loss, or revoked consent marks the connection `reauthorization_required` and stops infinite retries.

## Calendar behavior

The provider receives a deliberately minimal payload: a generic appointment title, start/end timestamps, timezone, consultation mode, and a non-sensitive CareLoop appointment reference. It never receives symptoms, diagnoses, notes, prescriptions, AI summaries, or medical history.

Confirmation queues a create job, cancellation queues delete, and the manual patient sync endpoint queues the appropriate operation without making a Google request in the HTTP transaction. Rescheduling creates a replacement CareLoop appointment, so Phase 6 deliberately uses **delete old event + create replacement event** rather than transferring the mapping. This keeps each calendar mapping attached to exactly one appointment.

Mappings are unique per appointment, user, and calendar. Durable jobs have deterministic idempotency keys. The worker claims due jobs with row locking (`SKIP LOCKED` on PostgreSQL), commits that claim before HTTP, recovers stale claims, and uses bounded exponential retry for timeouts, connection failures, 429s, and 5xx responses. Permanent failures retain only safe failure categories/messages. Google outages never roll back a CareLoop appointment.

Disconnect marks the connection disconnected, cancels pending/retry calendar jobs, and clears encrypted token material. It preserves CareLoop appointments and allows a later reconnect. Existing Google events are not proactively deleted during disconnect.

## Local setup

1. In Google Cloud Console, create or select a project and enable **Google Calendar API**.
2. Configure the OAuth consent screen. If it remains in testing mode, add each local tester as a test user.
3. Create an OAuth client of type **Web application**.
4. Add this exact authorized redirect URI:

   ```text
   http://localhost:8000/api/v1/integrations/google-calendar/callback
   ```

   If Google asks for an authorized JavaScript origin for your local browser setup, use:

   ```text
   http://localhost:5173
   ```

5. Generate a local Fernet key (do not commit its output):

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

6. Put only your own local values in `backend/.env`, then restart the backend:

   ```env
   CARELOOP_GOOGLE_CLIENT_ID=
   CARELOOP_GOOGLE_CLIENT_SECRET=
   CARELOOP_GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/integrations/google-calendar/callback
   CARELOOP_GOOGLE_TOKEN_ENCRYPTION_KEY=
   CARELOOP_GOOGLE_CALENDAR_SCOPES=https://www.googleapis.com/auth/calendar.events
   ```

The repository’s `.env.example` intentionally contains placeholders only. No real Google connection is claimed as tested until a developer completes this setup with their own credentials.

## Worker and tests

Run the worker once during development, or continuously in a supervised process:

```bash
cd backend
python -m app.cli.run_calendar_worker --once
python -m app.cli.run_calendar_worker
```

The `--once` command safely reports only aggregate counts. With no due work, it makes no Google request.

The automated OAuth, provider, worker, lifecycle, authorization, encryption, data-minimization, retry, and PostgreSQL-concurrency tests use fake providers or mocked HTTP transports. They never contact Google. A manual integration check, after local configuration, is: connect from the patient dashboard, confirm a fictional appointment, run the worker once, verify the minimal event in the selected calendar, cancel the appointment, run the worker again, and disconnect. Do not use real clinical information for this check.

## Trade-offs and evaluation notes

- The UI shows connection state and safe queued-sync feedback. The current API does not expose per-appointment mapping metadata, so it does not claim a durable per-event status it cannot retrieve.
- Calendar sync is asynchronous by design; an appointment remains confirmed even if provider synchronization fails.
- The callback destination is intentionally allowlisted rather than caller-controlled.
- A real Google test is a manual environment step, not an automated test, to avoid credentials and network calls in CI.
