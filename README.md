# CareLoop

CareLoop is an AI-powered healthcare appointment and follow-up manager for patients, doctors, and administrators. This repository currently contains **Phase 1 only**: the project foundation and role-based authentication.

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
│   │   ├── services/         # Authentication business rules
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
└── docs/phase-1-foundation.md
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
# Apply every migration
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

The command refuses to overwrite an existing email and hashes the supplied password. The example `.env.example` values are placeholders, not test credentials. Doctor account provisioning is intentionally deferred until an administrator workflow is designed; for Phase 1, doctor authorization is covered directly by tests.

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

Development has explicit local fallbacks. When `CARELOOP_ENVIRONMENT=production`, startup rejects the fallback database URL and an absent, short, or development JWT secret. No API key or external-service setting exists in Phase 1.

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

- No appointment, doctor-profile, availability, or leave-management behavior yet
- No LLM summaries, failure handling, patient-history retrieval, or RAG yet
- No reminders, workers, Redis, email provider, retry queue, or Google Calendar OAuth yet
- No password reset, email verification, refresh-token revocation store, or admin UI
- Placeholder dashboards have no clinical or operational data
- The health endpoint verifies connectivity, not deeper database readiness

## Roadmap after Phase 1 review

1. Doctor profiles, availability, and administrator-led doctor provisioning
2. Transactional, conflict-safe appointment booking and doctor leave conflict handling
3. LLM pre-visit summaries with graceful fallback and a small patient-history RAG step
4. Post-visit summaries stored in the database
5. Background medication reminders, durable retries, and SendGrid-compatible email delivery
6. Google Calendar OAuth 2.0 and appointment synchronization
7. Security hardening, observability, integration tests, and deployment preparation

The next phase should begin only after the foundation and authentication design have been reviewed.

