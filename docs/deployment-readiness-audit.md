# Deployment readiness audit

This audit records code-level readiness, not a production deployment. “Complete with operational configuration” means the code exists but requires provider credentials, domains, or managed infrastructure at deployment time.

| Requirement | Status | Evidence |
| --- | --- | --- |
| Backend API | Complete with operational configuration | `backend/app/main.py`, backend Docker image, `/api/v1/health/live` and `/api/v1/health/ready` |
| Frontend | Complete with operational configuration | `frontend/`, Vite production image, nginx history fallback |
| PostgreSQL | Complete with operational configuration | SQLAlchemy models, Alembic head `20260822_08`, Render/Compose database definitions |
| Patient/doctor/admin authorization | Complete | auth routes/services and authorization tests |
| Appointment lifecycle | Complete | appointment service/routes and lifecycle tests |
| Pre-visit LLM summary stored in DB | Complete with operational configuration | pre-visit models/services and LLM tests; requires enabled provider key |
| Post-visit LLM summary stored in DB | Complete with operational configuration | visit summary models/services and LLM tests; requires enabled provider key |
| Graceful deterministic LLM fallback | Complete | LLM/visit fallback tests and provider error classification |
| Controlled RAG/history retrieval | Complete | patient-isolation/RAG tests and visit services |
| Medication reminders | Complete | medication/reminder models and Phase 5 notification outbox |
| Email retries | Complete | notification worker claim/retry implementation and tests |
| Real SMTP delivery | Complete with operational configuration | SMTP provider tests; requires safe SMTP config/sender |
| Google Calendar OAuth 2.0 | Complete with operational configuration | Calendar routes/provider/connection models; requires HTTPS OAuth registration |
| Durable Calendar synchronization | Complete with operational configuration | Calendar sync jobs, mappings, worker CLI, migration `20260822_08`, worker tests |
| Security | Complete with operational configuration | production settings validation, encrypted OAuth tokens, HttpOnly/Secure cookie policy, explicit CORS validation |
| Tests | Complete | backend test suite, targeted provider/worker tests; PostgreSQL suite requires isolated `careloop_test` configuration |
| Documentation | Complete | README, Phase 5/6 docs, `.env.example`, this deployment guide |
| Deployment process | Complete with operational configuration | Dockerfiles, `render.yaml`, Compose simulation, GitHub Actions workflow, migration guidance |

Before production use, manually configure real domains/TLS, secrets, database backups, OAuth consent screen/redirect URI, approved email sender, provider accounts, worker scaling/monitoring, and a rollback rehearsal.
