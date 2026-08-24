# CareLoop

CareLoop is an AI-assisted healthcare appointment and continuity-of-care platform that connects booking, visit preparation, clinician-reviewed summaries, reminders, and calendar synchronization.

The core workflow remains usable when an LLM, email provider, or Calendar provider is unavailable: appointment state is persisted transactionally, provider work is queued, retries are bounded, and visit intelligence has a deterministic fallback.

## Problem

Healthcare appointment systems often stop at booking. Patient symptoms, visit preparation, clinical instructions, medication schedules, and follow-up actions remain fragmented across forms, messages, and calendars.

## Solution

CareLoop brings those steps into role-specific patient, doctor, and administrator workspaces. It provides concurrency-safe appointment booking, pre-visit care packets, clinician-controlled post-visit summaries, medication reminders, email notifications, Google Calendar synchronization, and durable retry/fallback mechanisms. AI assists with summarization; it does not replace clinician judgment or approval.

## System Architecture

```mermaid
flowchart TB
    UI["React + TypeScript + Vite"]
    API["FastAPI API"]
    DB[("PostgreSQL")]
    LLM["Groq / OpenAI-compatible LLM"]
    NW["Notification Worker"]
    CW["Calendar Worker"]
    EMAIL["SMTP / Resend / SendGrid / log"]
    GCAL["Google Calendar"]

    UI --> API
    API --> DB
    API --> LLM
    DB --> NW
    DB --> CW
    NW --> EMAIL
    CW --> GCAL
```

The API owns authorization and transactional domain changes. Workers claim durable jobs from PostgreSQL before contacting external providers, so provider outages do not hold application transactions open.

## Core capabilities

- Patient-only public registration and patient, doctor, and administrator authorization.
- Administrator-controlled doctor profiles, working hours, leave, availability, and demo-data tooling.
- Timezone-aware slot previews, short-lived holds, PostgreSQL overlap protection, confirmation, cancellation, and linked rescheduling.
- Structured symptoms, clinician-owned clinical records, prescriptions, pre-visit intelligence, and clinician-reviewed post-visit summaries.
- Patient-scoped history retrieval with stored source links and deterministic fallback when LLM generation is unavailable.
- Durable notification outbox with medication reminders, idempotency, retries, log/fake providers, SMTP, Resend, and SendGrid support.
- Optional patient-owned Google Calendar OAuth and durable create/update/delete synchronization.
- Secure password reset with hashed, expiring, single-use tokens and authentication-version invalidation.

## Technology stack

Backend: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL/psycopg, PyJWT, Argon2 via `pwdlib`, and Pytest.

Frontend: React, TypeScript, Vite, React Router, and Tailwind CSS.

## Quick start

### 1. Create a local PostgreSQL database

```sql
CREATE USER careloop WITH PASSWORD 'careloop';
CREATE DATABASE careloop OWNER careloop;
```

These credentials are for local development only.

### 2. Install and configure the backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
cp .env.example .env
```

Set a random `CARELOOP_JWT_SECRET` of at least 32 characters in the ignored `.env`, then apply the schema and start the API:

```bash
python -m alembic upgrade head
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`; interactive documentation is at `/docs`. Liveness and database readiness are exposed at `/api/v1/health/live` and `/api/v1/health/ready`.

### 3. Install and run the frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Set `VITE_API_URL` in the ignored frontend `.env` when the API is not at its default `http://localhost:8000/api/v1`.

## Workers and operations

Run workers continuously in deployed environments; use `--once` for a bounded local pass:

```bash
cd backend
source .venv/bin/activate
python -m app.cli.run_notification_worker
python -m app.cli.run_calendar_worker

# One bounded pass
python -m app.cli.run_notification_worker --once
python -m app.cli.run_calendar_worker --once
```

Apply migrations once per release, before starting application replicas:

```bash
python -m alembic upgrade head
python -m alembic current
```

The current migration head is `20260822_09`. Never point PostgreSQL concurrency tests at a development or production database; set an explicit dedicated `TEST_DATABASE_URL`.

For local fictional doctors, use `python -m app.cli.seed_demo_data` with `DEMO_DOCTOR_PASSWORD`. The seed is development-only and idempotent. Resetting those six demo accounts uses `python -m app.cli.reset_demo_doctor_passwords`.

## Selected API areas

All routes are prefixed with `/api/v1`.

| Area | Examples |
| --- | --- |
| Authentication | `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/forgot-password`, `/auth/reset-password` |
| Doctors and scheduling | `/doctors`, `/doctors/{id}/slots`, `/admin/doctors`, `/doctor/me/profile` |
| Appointments | `/appointments/holds`, `/appointments`, `/appointments/me`, cancellation and rescheduling routes |
| Visit intelligence | Patient summaries plus doctor review, regeneration, completion, clinical-record, prescription, approve, and reject routes |
| Notifications | `/notifications`, `/admin/notifications` |
| Google Calendar | `/integrations/google-calendar/status`, connect, callback, disconnect, and appointment sync routes |
| Health | `/health/live`, `/health/ready`, and `/health` |

## Configuration and provider boundaries

Backend variables use the `CARELOOP_` prefix and are documented in [backend/.env.example](backend/.env.example). Frontend variables use Vite's `VITE_` prefix and are documented in [frontend/.env.example](frontend/.env.example). Never commit `.env` files or place backend secrets in frontend variables.

The documented LLM example uses Groq's OpenAI-compatible endpoint:

```env
CARELOOP_LLM_PROVIDER=openai_compatible
CARELOOP_LLM_BASE_URL=https://api.groq.com/openai/v1
CARELOOP_LLM_MODEL=openai/gpt-oss-20b
```

LLM responses use a strict JSON schema and are validated again with Pydantic. Authentication/model errors are not retried; rate limits, timeouts, and transient server errors have bounded retry behavior. Email and Calendar providers similarly use sanitized failure categories and never receive clinical data beyond their allowlisted payloads.

## Tests

```bash
cd backend
source .venv/bin/activate
pytest

# PostgreSQL-only tests require a separate database
TEST_DATABASE_URL='postgresql+psycopg://user:password@localhost:5432/careloop_test' pytest -m postgresql

cd ../frontend
npm run build
```

Automated provider tests use fake providers or mocked HTTP transports. PostgreSQL fixtures create isolated schemas and refuse a URL that matches the development database.

## Documentation

Detailed implementation and operational notes remain under [`docs/`](docs/):

- [Deployment guide](docs/deployment.md) and [readiness audit](docs/deployment-readiness-audit.md)
- [Phase 1 foundation](docs/phase-1-foundation.md)
- [Phase 2A doctor scheduling](docs/phase-2a-doctor-scheduling.md)
- [Phase 2B appointment booking and concurrency](docs/phase-2b-appointment-booking.md)
- [Phase 3 visit intelligence](docs/phase-3-ai-visit-intelligence.md)
- [Phase 4 post-visit intelligence](docs/phase-4-post-visit-intelligence.md)
- [Phase 5 notifications and reminders](docs/phase-5-notifications-and-reminders.md)
- [Phase 6 Google Calendar](docs/phase-6-google-calendar.md)

## Project structure

```text
careloop/
├── backend/
│   ├── app/{api,cli,core,db,models,repositories,schemas,services}/
│   ├── alembic/versions/
│   └── tests/
├── frontend/src/{api,components,contexts,layouts,pages,routes,types}/
└── docs/
```

CareLoop is an assessment/demo application. Provider credentials, domain configuration, backups, monitoring, and deployment-specific security controls must be supplied and reviewed separately for any real environment.
