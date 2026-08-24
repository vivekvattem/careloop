# CareLoop

<img src="frontend/public/careloop-mark.svg" alt="CareLoop mark" width="44" />

CareLoop is an AI-assisted healthcare appointment and visit-continuity platform for patients, doctors, and administrators.

- Live application: [careloop-vivek-vattem.vercel.app](https://careloop-vivek-vattem.vercel.app/)
- API documentation: [Swagger UI](https://careloop-demo-api.onrender.com/docs)
- Repository validation: automated backend tests, mocked provider tests, PostgreSQL migration checks, and frontend production builds are included; see [Testing and Validation](#testing-and-validation).

## Problem

Appointment booking systems often stop at scheduling, leaving care context fragmented before and after visits. External AI, email, and Calendar providers can also fail; CareLoop keeps the core appointment workflow available when they do.

## Solution

CareLoop combines role-based healthcare workflows, concurrency-safe booking, doctor schedules and leave management, pre-visit AI summaries with limited patient-history retrieval, clinician-reviewed post-visit summaries, durable email and medication-reminder jobs, Google Calendar OAuth synchronization, and deterministic fallbacks. AI assists clinicians; it does not replace clinical judgment.

## Live Demo

| Component | URL |
| --- | --- |
| Frontend | https://careloop-vivek-vattem.vercel.app/ |
| Backend API | https://careloop-demo-api.onrender.com |
| Swagger documentation | https://careloop-demo-api.onrender.com/docs |
| Liveness | https://careloop-demo-api.onrender.com/api/v1/health/live |
| Readiness | https://careloop-demo-api.onrender.com/api/v1/health/ready |

This is a hiring-assessment demonstration. Free Render services may sleep during inactivity, so the first request after sleep can take longer. Core appointments remain stored in PostgreSQL if external integrations fail. Demo credentials are intentionally not published.

## Key Features

### Patient

- Registration, authentication, and password reset.
- Doctor discovery, timezone-aware slot previews, transactional holds, booking, cancellation, and rescheduling.
- Symptom submission, approved visit summaries, prescriptions, reminder controls, and Google Calendar connection.

### Doctor

- Schedule and appointment views with pre-visit care packets.
- Clinical records, prescriptions, visit completion, and post-visit summary review, regeneration, approval, and rejection.
- Private notes remain excluded from patient responses and LLM payloads.

### Administrator

- Doctor provisioning, working-hour and leave management, leave-conflict handling, appointment oversight, and notification-status visibility.

## System Architecture

```mermaid
flowchart TB
    Web["Vercel React frontend"] --> API["Render FastAPI demo service"]
    subgraph Demo["Combined Render process"]
        API --> App["API process"]
        API --> NW["Notification worker"]
        API --> CW["Calendar worker"]
    end
    App --> DB[("Render PostgreSQL")]
    NW <--> DB
    CW <--> DB
    App --> LLM["Groq-compatible LLM"]
    NW --> SMTP["Gmail SMTP"]
    CW --> GCal["Google Calendar OAuth/API"]
```

API transactions write durable notification and Calendar jobs to PostgreSQL. Workers claim those jobs later, so provider outages do not keep booking transactions open.

## Core Data Flow

```mermaid
flowchart TB
    Select["Patient selects doctor slot"] --> Hold["Time-limited database hold"]
    Hold --> Validate["Transactional schedule, leave, and conflict revalidation"]
    Validate --> Exclude["PostgreSQL exclusion constraint"]
    Exclude --> Commit["Appointment and durable outbox/sync jobs commit"]
    Commit --> Workers["Workers deliver email and Calendar changes independently"]
```

## AI and RAG Flow

```mermaid
flowchart TB
    Input["Symptoms and verified CareLoop history"] --> Retrieve["Limited retrieval and ranking"]
    Retrieve --> Prompt["Versioned prompt"]
    Prompt --> LLM["OpenAI-compatible LLM"]
    LLM --> Validate["Pydantic validation and safety checks"]
    Validate --> Store["Stored summary"]
    LLM --> Fallback["Deterministic fallback on failure"]
    Fallback --> Store
    Store --> Review["Clinician review for post-visit content"]
```

RAG sources are verified, patient-scoped CareLoop history—not unrestricted medical web content. The implementation uses bounded lexical retrieval, not a vector database or embeddings.

## Reliability Decisions

| Concern | Protection |
| --- | --- |
| Double booking | PostgreSQL range exclusion constraints, doctor locks, transactional revalidation |
| Slot competition | Short-lived database-backed holds with hashed tokens |
| Doctor leave conflicts | Read-only preview followed by explicit confirmed transactional resolution |
| LLM outage | Stored deterministic fallback; appointment workflow remains available |
| Email failure | Transactional outbox, idempotency keys, retries, exponential backoff |
| Calendar failure | Durable sync jobs; appointment status is independent of Google |
| Token security | Hashed reset/hold tokens and encrypted Google OAuth tokens |
| Authorization | Patient, doctor, and admin route-level enforcement |

## Technology Stack

React, TypeScript, Vite, Tailwind CSS, FastAPI, Python, SQLAlchemy, Alembic, PostgreSQL, JWT, Argon2, Groq through an OpenAI-compatible interface, SMTP email, Google Calendar OAuth 2.0, pytest, Docker, Render, and Vercel.

## Local Setup

Prerequisites: Python 3.12, Node.js, npm, and PostgreSQL (or Docker for the local database).

```bash
# Create a local database and install the backend
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
cp .env.example .env
python -m alembic upgrade head
uvicorn app.main:app --reload
```

Use a local PostgreSQL database matching `CARELOOP_DATABASE_URL` in the ignored `backend/.env`. Set a random `CARELOOP_JWT_SECRET` of at least 32 characters; never place real credentials in this README.

In separate terminals, run the durable workers:

```bash
cd backend
source .venv/bin/activate
python -m app.cli.run_notification_worker
python -m app.cli.run_calendar_worker
```

Then run the frontend:

```bash
cd frontend
npm install
npm run dev
```

The local API is at `http://localhost:8000`, Swagger is at `http://localhost:8000/docs`, and the frontend is at `http://localhost:5173`.

## Environment Configuration

[`backend/.env.example`](backend/.env.example) is the canonical backend reference; [`frontend/.env.example`](frontend/.env.example) documents Vite’s public values. Copy examples into ignored local `.env` files rather than inventing aliases.

| Group | Variables |
| --- | --- |
| Application, database, security | `CARELOOP_ENVIRONMENT`, `CARELOOP_DATABASE_URL`, `CARELOOP_JWT_SECRET`, token/hold durations |
| Frontend and CORS | `CARELOOP_FRONTEND_ORIGIN`, `CARELOOP_CORS_ORIGINS`, `CARELOOP_PUBLIC_API_URL`, `CARELOOP_COOKIE_SAMESITE`, `VITE_API_URL` |
| LLM | `CARELOOP_LLM_ENABLED`, `CARELOOP_LLM_PROVIDER`, `CARELOOP_LLM_API_KEY`, `CARELOOP_LLM_BASE_URL`, `CARELOOP_LLM_MODEL`, `CARELOOP_LLM_TIMEOUT_SECONDS` |
| SMTP and email | `CARELOOP_EMAIL_PROVIDER`, `CARELOOP_EMAIL_FROM_ADDRESS`, SMTP/Resend/SendGrid settings, `CARELOOP_EMAIL_TIMEOUT_SECONDS` |
| Google Calendar | `CARELOOP_GOOGLE_CALENDAR_ENABLED`, client credentials, redirect URI, token-encryption key, and scopes |
| Worker and retry | `CARELOOP_NOTIFICATION_POLL_SECONDS`, `CARELOOP_NOTIFICATION_MAX_ATTEMPTS`, `CARELOOP_NOTIFICATION_BASE_RETRY_SECONDS`, `CARELOOP_NOTIFICATION_STALE_CLAIM_SECONDS` |

Backend secrets belong only in ignored local files or the deployment secret store. Never expose them through Vite variables.

## API Documentation

- Deployed: [Swagger UI](https://careloop-demo-api.onrender.com/docs)
- Local: [http://localhost:8000/docs](http://localhost:8000/docs)
- Route groups: authentication, doctors and scheduling, appointments, visit intelligence, notifications, Calendar integrations, and health.

The generated OpenAPI document is the authoritative request and response contract.

## Database Schema

Alembic manages PostgreSQL schema evolution. The main domains are:

- Identity and authentication: users, password-reset tokens, and authorization state.
- Doctor scheduling: profiles, working hours, and leave.
- Appointments and holds: appointments, status history, symptoms, and short-lived slot holds.
- Clinical records and summaries: notes, prescriptions/items, pre-visit summaries, post-visit summaries, and verified care documents.
- Notifications and medication reminders: transactional outbox jobs and reminder schedules.
- Google Calendar: encrypted connections, OAuth state, event mappings, and durable sync jobs.

See [Phase 2B booking and concurrency](docs/phase-2b-appointment-booking.md), [Phase 3 visit intelligence](docs/phase-3-ai-visit-intelligence.md), [Phase 5 notifications](docs/phase-5-notifications-and-reminders.md), and [Phase 6 Google Calendar](docs/phase-6-google-calendar.md) for detailed design notes.

## LLM Prompts and Failure Handling

Pre-visit intent: “Analyse these symptoms and return an urgency level, chief complaint, and three suggested questions for the doctor.”

Post-visit intent: “Convert clinician-approved notes into a patient-friendly summary with the stored medication schedule and follow-up steps.”

Actual versioned prompts are in [`backend/app/services/prompts.py`](backend/app/services/prompts.py). Results are validated and stored in PostgreSQL. Provider failures never block valid bookings or visit completion; deterministic summaries persist as fallback; medications cannot be invented or changed by the LLM.

## Google Calendar Setup

1. Enable the Google Calendar API and configure an OAuth consent screen.
2. Create a Web OAuth client.
3. Add the deployed callback URI: `https://careloop-demo-api.onrender.com/api/v1/integrations/google-calendar/callback`.
4. Add the local development callback URI: `http://localhost:8000/api/v1/integrations/google-calendar/callback`.
5. Store the client ID, client secret, encryption key, scope, and redirect URI only in environment secrets.
6. Connect the Calendar from the patient dashboard.

Bookings remain valid if Calendar synchronization fails.

## Deployment

The frontend runs on Vercel. Render hosts PostgreSQL and one free demo web service, which supervises the API, notification worker, and Calendar worker after migrations run. This combined free-tier topology is appropriate for assessment/demo use; production should deploy independent API and worker services. See the [deployment guide](docs/deployment.md).

## Testing and Validation

```bash
cd backend
source .venv/bin/activate
pytest
TEST_DATABASE_URL='postgresql+psycopg://user:password@localhost:5432/careloop_test' pytest -m postgresql
python -m alembic current
python -m alembic check

cd ..
docker build -f backend/Dockerfile -t careloop-backend .

cd frontend
npm run build
```

Provider tests use fake providers or mocked transports. PostgreSQL tests require an explicitly isolated database and reject the development database URL.

## Project Structure

```text
careloop/
├── backend/app/
├── backend/alembic/
├── backend/tests/
├── frontend/src/
├── docs/
├── render.yaml
└── docker-compose.yml
```

## Design Documentation

- [Deployment guide](docs/deployment.md)
- [Deployment readiness audit](docs/deployment-readiness-audit.md)
- [Visit intelligence](docs/phase-3-ai-visit-intelligence.md)
- [Notifications and reminders](docs/phase-5-notifications-and-reminders.md)
- [Google Calendar](docs/phase-6-google-calendar.md)

## Safety and Scope

CareLoop is an assessment/demo application, not a medical diagnosis system. AI output is assistive and must not replace clinician judgment. Use only fictional data in demonstrations and do not upload real patient information.
