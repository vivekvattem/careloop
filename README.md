# CareLoop

CareLoop is an AI-powered healthcare appointment and follow-up manager for patients, doctors, and administrators. The repository contains Phase 1 authentication, Phase 2A scheduling, Phase 2B concurrency-safe booking, and **Phase 3 visit intelligence with controlled patient-history RAG**.

## Phase 6 Google Calendar

Phase 6 adds an optional patient-owned Google Calendar authorization-code integration with encrypted token storage, minimal event payloads, durable idempotent synchronization jobs, and a patient dashboard connection section. Calendar work never determines whether a CareLoop appointment is confirmed. See [Phase 6 documentation](docs/phase-6-google-calendar.md) for local Google Cloud setup, security behavior, worker commands, testing, and the manual integration procedure.

```bash
cd backend
python -m app.cli.run_calendar_worker --once
```

## Phase 5 notifications

Phase 5 adds a durable database outbox and medication reminder worker. In development, run `python -m app.cli.run_notification_worker --once`; the default log provider performs no network delivery. See `docs/phase-5-notifications-and-reminders.md` for retry, idempotency, and optional provider configuration.

## What Phase 1 includes

- Patient-only public registration with normalized, unique email addresses
- Argon2 password hashing; password hashes never leave the backend
- JWT access tokens and rotating refresh tokens
- HTTP-only refresh cookie and in-memory frontend access token
- Active-user and patient/doctor/admin role checks
- Current-user, health, logout, and protected role-verification endpoints
- Environment-driven admin bootstrap CLI (no public privileged registration)
- PostgreSQL-ready SQLAlchemy models and an initial Alembic migration
- React authentication context, protected routing, and placeholder dashboards
- Deterministic backend tests with no external calls

## What Phase 2A includes

- Atomic, administrator-controlled doctor account and profile provisioning
- Doctor profile editing, activation, and booking-availability controls
- Multiple non-overlapping working intervals per weekday
- Administrator-managed full-day leave
- Paginated patient discovery with case-insensitive specialisation search
- Read-only doctor self-service profile, schedule, and leave views
- Deterministic timezone-aware slot previews with past, leave, and inactive filtering
- Functional role-specific frontend workflows for all three roles

The Phase 2A slot endpoint remains a preview. Phase 2B uses those validated slots to create short-lived holds and confirmed appointment records.

## What Phase 2B includes

- Five-minute, configurable, opaque-token slot holds
- Structured patient symptom submission before confirmation
- Transactional appointment confirmation and atomic rescheduling
- Patient cancellation with status history and restored availability
- Patient and doctor appointment views plus a paginated admin list
- Leave-conflict preview and confirmed `reschedule_required` transitions
- PostgreSQL `btree_gist` exclusion constraints preventing overlapping active holds and appointments
- Deterministic concurrent PostgreSQL tests using isolated schemas

## What Phase 3 includes

- Structured clinical notes and prescriptions controlled only by the assigned doctor
- Compulsory pre-visit and post-visit generation with deterministic fallback
- Groq as the documented primary provider through its OpenAI-compatible endpoint
- Strict JSON Schema responses followed by Pydantic validation
- Patient-scoped PostgreSQL history retrieval with stored source links
- Doctor review, edit, approval, rejection, and manual regeneration
- Patient access only to approved post-visit content

## What Phase 4 includes

- Visit treatment-plan, private-note, start, and completion metadata without duplicating Phase 3 clinical records
- Prescription-item active state and database-level nonblank medication/dosage validation
- Doctor-only visit aliases and individual prescription-item operations
- Persisted post-visit safety disclaimer and prescription-fidelity failure category
- Transactional appointment completion followed by out-of-transaction LLM generation
- Bounded, row-locked regeneration protection and patient-safe approved summaries

See [Phase 4 documentation](docs/phase-4-post-visit-intelligence.md) for lifecycle, authorization, manual testing, and trade-offs.

## Technology stack

The backend uses Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL/psycopg, PyJWT, Argon2 via `pwdlib`, and Pytest. The frontend uses React, TypeScript, Vite, React Router, and Tailwind CSS. Direct dependencies are pinned in their respective manifests.

## Project structure

```text
careloop/
├── backend/
│   ├── alembic/              # Versioned database migrations
│   ├── app/
│   │   ├── api/              # Routes and request dependencies
│   │   ├── cli/              # Non-public administration commands
│   │   ├── core/             # Settings and security primitives
│   │   ├── db/               # SQLAlchemy base, engine, and sessions
│   │   ├── models/           # Database table mappings
│   │   ├── repositories/     # Database queries and persistence
│   │   ├── schemas/          # API validation and response shapes
│   │   ├── services/         # Authentication, provisioning, and slot rules
│   │   └── main.py           # FastAPI application assembly
│   ├── tests/
│   ├── .env.example
│   ├── alembic.ini
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── api/              # Typed backend client
│   │   ├── components/       # Shared interface pieces
│   │   ├── contexts/         # Authentication state
│   │   ├── layouts/          # Public and signed-in shells
│   │   ├── pages/            # Route-level screens
│   │   ├── routes/           # Route guards
│   │   └── types/            # Shared TypeScript domain types
│   ├── .env.example
│   └── package.json
└── docs/
    ├── phase-1-foundation.md
    ├── phase-2a-doctor-scheduling.md
    ├── phase-2b-appointment-booking.md
    └── phase-3-ai-visit-intelligence.md
```

The additional `backend/app/cli` directory is intentional: it keeps privileged bootstrap operations separate from public HTTP routes.

## PostgreSQL setup

Install PostgreSQL locally, start it, and create a development role and database. Run these statements as a PostgreSQL superuser:

```sql
CREATE USER careloop WITH PASSWORD 'careloop';
CREATE DATABASE careloop OWNER careloop;
```

The example credentials are for local development only. Use managed secrets and unique credentials in deployed environments.

## Run the backend

Python 3.12 is required.

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
cp .env.example .env
```

Replace `CARELOOP_JWT_SECRET` in `.env` with a random value of at least 32 characters. Then apply the schema and start the API:

```bash
python -m alembic upgrade head
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000`; interactive documentation is at `http://localhost:8000/docs`.

### Alembic commands

```bash
# Apply all migrations through Phase 3
python -m alembic upgrade head

# Create a migration after changing models; inspect the file before applying it
python -m alembic revision --autogenerate -m "describe the schema change"

# Roll back one migration
python -m alembic downgrade -1

# Show current migration state
python -m alembic current
```

Alembic reads the same `CARELOOP_DATABASE_URL` as the application; the URL in `alembic.ini` is only a harmless local fallback.

## Bootstrap an admin

Public registration always produces a patient. After migrations are applied, set the three bootstrap environment variables in your local `.env` and run:

```bash
cd backend
source .venv/bin/activate
python -m app.cli.create_admin
```

The command refuses to overwrite an existing email and hashes the supplied password. The example `.env.example` values are placeholders, not test credentials.

## Provision doctors

Sign in as an administrator and use the Doctor Management screen, or send `POST /api/v1/admin/doctors` with the account and profile fields. The backend fixes the new user's role to `doctor`, normalizes the email, hashes the initial password, and creates both records in one transaction. If profile creation fails, the user insert is rolled back. There is no public doctor-registration endpoint.

### Seed fictional demo doctors

For local demonstrations, seed six fictional doctors covering Cardiology, Dermatology, General Medicine, Paediatrics, Neurology, and Orthopaedics:

```bash
cd backend
source .venv/bin/activate
read -s DEMO_DOCTOR_PASSWORD
export DEMO_DOCTOR_PASSWORD
python -m app.cli.seed_demo_data
unset DEMO_DOCTOR_PASSWORD
```

Use a password that satisfies the normal rule: at least 10 characters with uppercase and lowercase letters and a number. The command never prints the password. It creates Monday–Saturday schedules in `Asia/Kolkata`, plus one future leave date per doctor.

The seed is idempotent: an existing demo email is skipped, existing records are never deleted, and the final output reports created and skipped counts. It refuses to run when either `ENVIRONMENT=production` or CareLoop's configured environment is production. The six demo login emails use the `@demo.careloop` domain and are defined in `app/cli/seed_demo_data.py`; they all use the password supplied at execution time.

To reset the password for exactly those six known demo doctor accounts:

```bash
cd backend
source .venv/bin/activate
read -s DEMO_DOCTOR_PASSWORD
export DEMO_DOCTOR_PASSWORD
python -m app.cli.reset_demo_doctor_passwords
unset DEMO_DOCTOR_PASSWORD
```

The reset command uses the normal Argon2 password utility and repository/session workflow. It never prints the password or resulting hashes, ignores every account outside the six-email allowlist, and reports only updated and skipped totals. Missing, non-doctor, or already-matching demo accounts are skipped. Like the seed command, it refuses to open the database in production.

## Phase 2A endpoints

```text
POST   /api/v1/admin/doctors
GET    /api/v1/admin/doctors
GET    /api/v1/admin/doctors/{doctor_id}
PATCH  /api/v1/admin/doctors/{doctor_id}
POST   /api/v1/admin/doctors/{doctor_id}/working-hours
PATCH  /api/v1/admin/doctors/{doctor_id}/working-hours/{working_hour_id}
DELETE /api/v1/admin/doctors/{doctor_id}/working-hours/{working_hour_id}
POST   /api/v1/admin/doctors/{doctor_id}/leave
DELETE /api/v1/admin/doctors/{doctor_id}/leave/{leave_id}

GET    /api/v1/doctors
GET    /api/v1/doctors/{doctor_id}
GET    /api/v1/doctors/{doctor_id}/slots?date=YYYY-MM-DD

GET    /api/v1/doctor/me/profile
GET    /api/v1/doctor/me/schedule
GET    /api/v1/doctor/me/leave
```

Admin routes require the admin role, discovery routes require the patient role, and `/doctor/me` routes derive the profile from the authenticated doctor rather than accepting another doctor's ID.

## Slot preview behavior

The service finds the requested weekday's intervals in the doctor's IANA timezone and divides each interval by the configured duration. It drops partial final slots, already-started slots, duplicates, leave dates, and all slots for inactive or unavailable doctors. Results are chronological, timezone-aware ISO-8601 timestamps.

Generated slots are not guarantees. Confirmation atomically revalidates appointments, active holds, schedule, doctor state, and leave.

## Appointment booking flow

1. The patient previews slots; this is never a guarantee.
2. `POST /api/v1/appointments/holds` revalidates the schedule and creates a five-minute hold. Only a SHA-256 hash of the random token is stored.
3. `POST /api/v1/appointments` locks and verifies the hold, rechecks doctor/schedule/leave/conflicts, creates the appointment, symptom submission and history, then consumes the hold in one commit.
4. PostgreSQL exclusion constraints are the final defense if concurrent requests race.

`CARELOOP_SLOT_HOLD_MINUTES` configures hold lifetime and defaults to `5`. Expired holds are lazily marked during relevant requests; no cleanup worker is required for correctness.

### Appointment endpoints

```text
POST /api/v1/appointments/holds
POST /api/v1/appointments
GET  /api/v1/appointments/me
GET  /api/v1/appointments/{appointment_id}
POST /api/v1/appointments/{appointment_id}/cancel
POST /api/v1/appointments/{appointment_id}/reschedule

GET  /api/v1/doctor/me/appointments
GET  /api/v1/doctor/me/appointments/{appointment_id}
GET  /api/v1/admin/appointments
GET  /api/v1/admin/doctors/{doctor_id}/leave-conflicts?date=YYYY-MM-DD
```

Cancellation changes the original row to `cancelled`, which removes it from the active-overlap constraint. Rescheduling creates a linked replacement and copies the original symptom submission; it never overwrites the original appointment's time.

When leave affects appointments, the preview endpoint makes no changes. Leave creation returns `409` until repeated with `?confirm_conflicts=true`; confirmed application creates the leave, marks every active conflict `reschedule_required`, and records history in one transaction.

### PostgreSQL concurrency tests

Use a dedicated test database URL whenever possible:

```bash
cd backend
source .venv/bin/activate
export TEST_DATABASE_URL='postgresql+psycopg://user:password@localhost:5432/careloop_test'
pytest -m postgresql
unset TEST_DATABASE_URL
```

The fixture creates a randomly named schema and drops only that schema. Tests refuse to run when `TEST_DATABASE_URL` equals the configured development database URL. Never point it at development or production.

## Phase 3 visit-intelligence flow

Appointment confirmation commits the appointment, original symptoms, a pending pre-visit record, and a patient-scoped symptom document. Only afterward does an in-process background task open a new session and attempt generation. Completion follows the same boundary: clinical note, exact structured prescription, completed status, history, and pending post summary commit before any provider request.

Groq is the documented primary provider, but the implementation uses a small provider interface rather than a Groq-specific SDK:

```env
CARELOOP_LLM_PROVIDER=openai_compatible
CARELOOP_LLM_API_KEY=
CARELOOP_LLM_BASE_URL=https://api.groq.com/openai/v1
CARELOOP_LLM_MODEL=openai/gpt-oss-20b
CARELOOP_LLM_TIMEOUT_SECONDS=8
```

Base URL and model are environment-configurable. A missing key never prevents startup or clinical work; it produces a useful deterministic fallback. Groq requests use `response_format.type=json_schema` with `strict=true`, closed objects, required properties, and nullable unions. Responses are validated again with Pydantic.

`401` authentication and `404` model errors are never retried. Rate limits, timeouts, and transient `5xx` errors are retried at most once. Malformed or schema-invalid output is not retried. Stored failures contain only sanitized categories/messages—never prompts, clinical text, keys, tokens, or raw provider payloads.

Prompt versions are `pre_visit_v1` and `post_visit_v1`. Exact prompts are documented in [Phase 3 visit intelligence](docs/phase-3-ai-visit-intelligence.md) and defined in `backend/app/services/prompts.py`.

### Phase 3 endpoints

```text
GET  /api/v1/appointments/{id}/pre-visit-summary
GET  /api/v1/appointments/{id}/post-visit-summary

GET  /api/v1/doctor/me/appointments/{id}/pre-visit-summary
POST /api/v1/doctor/me/appointments/{id}/pre-visit-summary/regenerate
POST /api/v1/doctor/me/appointments/{id}/complete
GET  /api/v1/doctor/me/appointments/{id}/clinical-record
PUT  /api/v1/doctor/me/appointments/{id}/clinical-record
GET  /api/v1/doctor/me/appointments/{id}/post-visit-summary
POST /api/v1/doctor/me/appointments/{id}/post-visit-summary/regenerate
POST /api/v1/doctor/me/appointments/{id}/post-visit-summary/approve
POST /api/v1/doctor/me/appointments/{id}/post-visit-summary/reject
```

Retrieval-augmented generation does not require a vector database; CareLoop retrieves patient-scoped historical context through PostgreSQL search before generation. SQL filters patient ownership, excludes the current appointment and unverified content, ranks relevance/source reliability/recency, and limits context to three records. Source relationships remain inspectable by the assigned doctor.

Post-visit medication schedules are checked against the stored prescription exactly. The doctor may edit explanatory and follow-up text, but prescription-derived content remains authoritative. Patients receive only the approved content, never raw notes or pending/rejected output.

Manual regeneration recovers pending or fallback records. In-process background tasks are best-effort and not durable; Phase 4 should replace them with a persistent outbox/worker.

### Optional live Groq check

Set a non-production API key locally, start the application, book a fictional test appointment, and use the doctor regeneration action. Inspect only the stored status/category; do not print provider output containing patient data. Automated tests always use fake or mock transports and never call Groq.

## Run the frontend

Node.js 20 or newer is recommended.

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Open `http://localhost:5173`. `VITE_API_URL` must point to the backend API prefix, normally `http://localhost:8000/api/v1`.

## Authentication storage decision

The backend sends the long-lived refresh token as an HTTP-only, `SameSite=Lax` cookie. Browser JavaScript cannot read it. The short-lived access token lives only in React memory and is sent as a Bearer token; refreshing the page obtains a new one through the cookie. This is safer than putting either token in `localStorage`.

Production cookies are marked `Secure`. A deployment with frontend and API on unrelated sites should additionally use a narrowly scoped cross-site cookie configuration plus explicit CSRF protection. Production should also persist refresh-token identifiers so individual sessions can be revoked; Phase 1 logout clears the browser cookie but does not maintain a server-side revocation list.

## Environment configuration

Backend settings use the `CARELOOP_` prefix and are documented in `backend/.env.example`. Frontend variables use Vite's `VITE_` prefix and are documented in `frontend/.env.example`. Never commit `.env` files.

Development has explicit local fallbacks. When `CARELOOP_ENVIRONMENT=production`, startup rejects the fallback database URL and an absent, short, or development JWT secret. LLM configuration remains optional because deterministic fallback is part of normal operation.

## Tests and checks

```bash
cd backend
source .venv/bin/activate
pytest
python -c "from app.main import app; print(app.title)"

cd ../frontend
npm run build
```

Fast business and HTTP tests use an in-memory SQLite engine. Marked PostgreSQL tests use separate connections and randomly named schemas for real exclusion-constraint races and the isolated migration downgrade/upgrade round trip.

## Current limitations

- In-process summary generation is not durable across process termination
- RAG uses lexical PostgreSQL search rather than embeddings or semantic vectors
- Deterministic urgency uses submitted severity bands only and is not diagnostic
- No reminders, durable workers, Redis, email provider, retry queue, or Google Calendar OAuth yet
- No password reset, email verification, or refresh-token revocation store
- Working-hour overlap is service-enforced; exact duplicates and invalid ranges are also database-constrained
- Hold expiration uses lazy cleanup; a future worker may remove old records for maintenance, not correctness
- Slot previews do not resolve daylight-saving fold/gap policy beyond Python's IANA timezone conversion
- The health endpoint verifies connectivity, not deeper database readiness

## Roadmap after Phase 3 review

1. Transactional outbox and durable worker processing for pending summaries
2. Medication reminder jobs derived directly from structured prescription times
3. SendGrid-compatible delivery with retries and delivery history
4. Google Calendar OAuth 2.0 and appointment synchronization
5. Security hardening, observability, integration tests, and deployment preparation

Email, reminder workers, and Calendar remain intentionally deferred until Phase 4.
