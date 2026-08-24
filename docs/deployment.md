# Production deployment

CareLoop's recommended production topology is four independently scalable processes sharing one PostgreSQL database: the FastAPI API, the notification worker, the Calendar-sync worker, and the static React frontend. Deploying only the API is incomplete: email and Calendar jobs remain queued until both workers are running.

## Free assessment topology

`render.yaml` is deliberately a constrained hiring-assessment Blueprint: Render hosts one free PostgreSQL database and one free backend web service. The backend runs `python -m app.cli.run_demo_service`, which migrates the database and supervises the API, notification worker, and Calendar worker. It co-locates those processes only because Render Free does not support background-worker services. The React/Vite frontend is hosted separately on Vercel. The independent commands below remain the production topology.

PostgreSQL still durably stores notification-outbox and Calendar-sync jobs. If the free web service sleeps or is restarted, processing pauses; pending jobs remain in PostgreSQL and resume when the service starts again. Provider failures do not invalidate appointments. Free Render Postgres is temporary (currently expires 30 days after creation) and this layout is not suitable for high-availability healthcare production or long-term production data.

The demo supervisor runs `python -m alembic upgrade head` once before it starts children. A migration failure prevents startup; it does not seed data, create an administrator, or perform a downgrade. In production, run migrations in a dedicated release/pre-deploy step before independently deploying API and worker replicas.

## Container commands

The backend image defaults to the API command and honours the platform `PORT`:

```sh
python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
```

Run exactly one migration release/pre-deploy action before replicas begin serving traffic:

```sh
python -m alembic upgrade head
```

Run the workers continuously (without `--once`):

```sh
python -m app.cli.run_notification_worker
python -m app.cli.run_calendar_worker
```

The checked-in Render Blueprint is the free assessment topology. For production, configure every required secret independently for the API and each worker; do not assume a secret configured on the API is inherited by workers.

### Render assessment deployment

1. Create a Blueprint from this repository. It creates only `careloop-demo-api` and `careloop-postgres` on Render.
2. Deploy the frontend as a Vercel project rooted at `frontend/`. Vercel uses `frontend/vercel.json` for React Router fallback while leaving paths containing a file extension (JavaScript, CSS, images, fonts, and so on) to static-file handling.
3. In Vercel, set the public build-time variable `VITE_API_URL` to `https://<backend-host>/api/v1`, where `<backend-host>` is the Render backend hostname.
4. In the Render backend service, manually configure `CARELOOP_FRONTEND_ORIGIN` to the final Vercel HTTPS origin (for example, `https://careloop-demo.vercel.app`) and set `CARELOOP_CORS_ORIGINS` to that same exact origin. Keep `CARELOOP_COOKIE_SAMESITE=lax` unless cross-site cookies genuinely require `none`; set `CARELOOP_PUBLIC_API_URL` to the Render HTTPS API origin when required by the current cookie/Calendar settings.
5. Leave LLM, email, and Calendar integrations disabled unless their required non-placeholder configuration has been supplied through the Render secret store. If Calendar OAuth is enabled, register `https://<backend-host>/api/v1/integrations/google-calendar/callback` on the Render backend; it does not move to Vercel.
6. After deployment, use the liveness and readiness checks below. Do not seed demo data or create an administrator automatically.

## Provisioning order

1. Create managed PostgreSQL, restrict network access, enable automated backups, and record the TLS-capable database URL as `CARELOOP_DATABASE_URL`.
2. Set production environment values in the provider secret store, using the matrix below. Keep `backend/.env` local and ignored.
3. Run the migration command once, after taking a restorable database backup.
4. Deploy the API and check `/api/v1/health/live` then `/api/v1/health/ready`.
5. Deploy both workers and confirm their concise startup/claim logs contain no credentials or clinical content.
6. Build and deploy the Vercel frontend with only public `VITE_API_URL=https://api.example.invalid/api/v1` configured at build time. Render hosts the API and workers; Vercel hosts the browser application.

Never run `alembic upgrade head` concurrently from API and worker replicas. A downgrade is an operational decision: first stop application writes, take and validate a backup, review the individual migration's downgrade safety, then deploy the previous compatible application version. Prefer forward corrective migrations for production data.

## Production browser and OAuth setup

Use HTTPS custom domains for the Vercel frontend and Render API. Set `CARELOOP_FRONTEND_ORIGIN` to the exact final Vercel origin, and set `CARELOOP_CORS_ORIGINS` to explicit comma-separated browser origins that include it. Credentialed CORS cannot use `*`.

Refresh-token cookies are HttpOnly; production sets the Secure flag. Use `CARELOOP_COOKIE_SAMESITE=none` only when frontend and API require cross-site cookies, and only with a HTTPS `CARELOOP_PUBLIC_API_URL`. For same-site subdomains, `lax` is normally preferable.

Register the exact HTTPS `CARELOOP_GOOGLE_REDIRECT_URI` on the Render backend in Google Cloud OAuth: `https://<backend-host>/api/v1/integrations/google-calendar/callback`. Enable Calendar only after setting a distinct Fernet `CARELOOP_GOOGLE_TOKEN_ENCRYPTION_KEY` and non-placeholder Google client credentials. Do not put OAuth credentials, tokens, API keys, App Passwords, or Fernet keys in source control or frontend variables.

For Gmail SMTP, use an App Password only where the Google account permits it; ordinary account passwords are not supported. For broader delivery use a verified sender/domain with SMTP, Resend, or SendGrid. Resend's onboarding sender may be restricted to the account email until a domain is verified.

## Environment-variable matrix

| Variable | Required when | Classification | API | notification worker | Calendar worker | frontend |
| --- | --- | --- | --- | --- | --- | --- |
| `CARELOOP_DATABASE_URL` | Always | secret | yes | yes | yes | no |
| `CARELOOP_JWT_SECRET` | Always, 32+ random chars | secret | yes | no | no | no |
| `CARELOOP_FRONTEND_ORIGIN`, `CARELOOP_CORS_ORIGINS` | API | public configuration | yes | no | no | no |
| `CARELOOP_PUBLIC_API_URL`, `CARELOOP_COOKIE_SAMESITE` | cross-site cookies/Calendar OAuth | public configuration | yes | no | no | no |
| `CARELOOP_LLM_ENABLED`, `CARELOOP_LLM_PROVIDER`, `CARELOOP_LLM_BASE_URL`, `CARELOOP_LLM_MODEL`, `CARELOOP_LLM_TIMEOUT_SECONDS` | LLM enabled | configuration | yes | no | no | no |
| `CARELOOP_LLM_API_KEY` | LLM enabled | secret | yes | no | no | no |
| `CARELOOP_EMAIL_PROVIDER`, `CARELOOP_EMAIL_FROM_ADDRESS`, `CARELOOP_EMAIL_TIMEOUT_SECONDS` | email | configuration | yes | yes | no | no |
| `CARELOOP_SENDGRID_API_KEY`, `CARELOOP_RESEND_API_KEY` | selected provider | secret | no | yes | no | no |
| `CARELOOP_SMTP_HOST`, `CARELOOP_SMTP_PORT`, `CARELOOP_SMTP_USE_STARTTLS` | SMTP selected | configuration | no | yes | no | no |
| `CARELOOP_SMTP_USERNAME`, `CARELOOP_SMTP_PASSWORD` | authenticated SMTP; supply both or neither | secret | no | yes | no | no |
| `CARELOOP_EMAIL_DELIVERY_REQUIRED` | production real delivery policy | configuration | yes | yes | no | no |
| `CARELOOP_GOOGLE_CALENDAR_ENABLED`, `CARELOOP_GOOGLE_CLIENT_ID`, `CARELOOP_GOOGLE_REDIRECT_URI`, `CARELOOP_GOOGLE_CALENDAR_SCOPES` | Calendar enabled | configuration | yes | no | yes | no |
| `CARELOOP_GOOGLE_CLIENT_SECRET`, `CARELOOP_GOOGLE_TOKEN_ENCRYPTION_KEY` | Calendar enabled | secret | yes | no | yes | no |
| `CARELOOP_NOTIFICATION_POLL_SECONDS`, `CARELOOP_NOTIFICATION_MAX_ATTEMPTS`, `CARELOOP_NOTIFICATION_BASE_RETRY_SECONDS`, `CARELOOP_NOTIFICATION_STALE_CLAIM_SECONDS` | worker polling/retry | configuration | no | yes | yes | no |
| `VITE_API_URL` | frontend build | public | no | no | no | yes |

`backend/.env.example` contains placeholders only. Production secrets belong in the deployment provider's secret manager, never in a Vite variable.

## Local container simulation

`docker compose up --build` is a local-only topology with PostgreSQL, API, both workers, and frontend. It deliberately does **not** read `backend/.env`. If local overrides are needed, create the ignored `backend/.env.compose` with placeholder-only or fake/log-provider values. Compose deliberately supplies no real Google, email, or LLM key. Run migrations once with `docker compose run --rm api python -m alembic upgrade head` before normal traffic. Avoid printing resolved Compose configuration when any secret-bearing env file is present.

## Smoke tests and troubleshooting

After deployment, check liveness, readiness, a sign-in/refresh flow from the approved frontend origin, a test appointment, and worker logs. Do not use production patient data for smoke checks.

```sh
curl -fsS https://api.example.invalid/api/v1/health/live
curl -fsS https://api.example.invalid/api/v1/health/ready
```

Readiness only checks the database; it intentionally does not call Groq, Google, SMTP, Resend, or SendGrid. Pending jobs usually mean a missing worker, database connectivity issue, or provider configuration error. Check the safe job failure category and worker logs, not raw provider payloads.

For rollback, stop or scale down workers before a database restore, restore a tested backup, deploy the matching compatible application image, then re-enable workers. Confirm queued job handling/idempotency before replaying work.
