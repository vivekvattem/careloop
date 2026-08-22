# CareLoop

CareLoop is an AI-powered healthcare appointment and follow-up manager for patients, doctors, and administrators. The repository currently contains Phase 1 authentication and **Phase 2A doctor profiles and scheduling foundations**.

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

Slot output is a preview only. No appointment, hold, or booking record is created.

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
    └── phase-2a-doctor-scheduling.md
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
# Apply Phase 1 and Phase 2A migrations
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

Generated slots are not guarantees. Phase 2B must atomically exclude appointments and active holds when booking.

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

Development has explicit local fallbacks. When `CARELOOP_ENVIRONMENT=production`, startup rejects the fallback database URL and an absent, short, or development JWT secret. No API key or external-service setting exists through Phase 2A.

## Tests and checks

```bash
cd backend
source .venv/bin/activate
pytest
python -c "from app.main import app; print(app.title)"

cd ../frontend
npm run build
```

Tests use an in-memory SQLite engine to isolate business and HTTP behavior. PostgreSQL remains the runtime database and Alembic migration target; applying the migration to PostgreSQL is the integration check for dialect-specific behavior.

## Current limitations

- No appointment booking, availability holds, or appointment conflict checks yet
- No LLM summaries, failure handling, patient-history retrieval, or RAG yet
- No reminders, workers, Redis, email provider, retry queue, or Google Calendar OAuth yet
- No password reset, email verification, or refresh-token revocation store
- Working-hour overlap is service-enforced; exact duplicates and invalid ranges are also database-constrained
- Slot previews do not account for daylight-saving ambiguities beyond Python's IANA timezone conversion
- The health endpoint verifies connectivity, not deeper database readiness

## Roadmap after Phase 2A review

1. Transactional, conflict-safe appointment booking, short-lived slot holds, cancellation, and doctor-leave conflict handling
2. LLM pre-visit summaries with graceful fallback and a small patient-history RAG step
3. Post-visit summaries stored in the database
4. Background medication reminders, durable retries, and SendGrid-compatible email delivery
5. Google Calendar OAuth 2.0 and appointment synchronization
6. Security hardening, observability, integration tests, and deployment preparation

Appointment booking is the next phase and should begin only after Phase 2A has been reviewed.
