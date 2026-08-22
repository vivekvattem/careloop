# CareLoop

CareLoop is an AI-powered healthcare appointment and follow-up manager for patients, doctors, and administrators. The repository currently contains Phase 1 authentication, **Phase 2A doctor profiles and scheduling foundations**, and **Phase 2B concurrency-safe appointment booking**.

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
    └── phase-2b-appointment-booking.md
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
alembic upgrade head
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000`; interactive documentation is at `http://localhost:8000/docs`.

### Alembic commands

```bash
# Apply all migrations through Phase 2B
alembic upgrade head

# Create a migration after changing models; inspect the file before applying it
alembic revision --autogenerate -m "describe the schema change"

# Roll back one migration
alembic downgrade -1

# Show current migration state
alembic current
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

The fixture creates a randomly named schema and drops only that schema. For an explicit local-only run against the configured development server—still using an isolated schema—use `CARELOOP_RUN_POSTGRES_TESTS=1`. Never point `TEST_DATABASE_URL` at production.

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

Development has explicit local fallbacks. When `CARELOOP_ENVIRONMENT=production`, startup rejects the fallback database URL and an absent, short, or development JWT secret. No API key or external-service setting exists through Phase 2B.

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

- No appointment completion workflow or clinician-authored visit notes yet
- No LLM summaries, failure handling, patient-history retrieval, or RAG yet
- No reminders, workers, Redis, email provider, retry queue, or Google Calendar OAuth yet
- No password reset, email verification, or refresh-token revocation store
- Working-hour overlap is service-enforced; exact duplicates and invalid ranges are also database-constrained
- Hold expiration uses lazy cleanup; a future worker may remove old records for maintenance, not correctness
- Slot previews do not resolve daylight-saving fold/gap policy beyond Python's IANA timezone conversion
- The health endpoint verifies connectivity, not deeper database readiness

## Roadmap after Phase 2B review

1. LLM pre-visit summaries with graceful fallback and a small patient-history RAG step
2. Post-visit summaries stored in the database
3. Background medication reminders, durable retries, and SendGrid-compatible email delivery
4. Google Calendar OAuth 2.0 and appointment synchronization
5. Security hardening, observability, integration tests, and deployment preparation

Notifications and AI are intentionally deferred until after Phase 2B review.
