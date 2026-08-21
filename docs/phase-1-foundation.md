# Phase 1 foundation: how it works

This guide explains the decisions you should be able to defend, not just the commands needed to run the project.

## 1. What FastAPI does

FastAPI is the backend's HTTP framework. It matches a URL and HTTP method to a Python route function, validates incoming data through Pydantic, resolves dependencies such as a database session or current user, and serializes the result into JSON. It also generates an OpenAPI description and interactive API documentation from the same types.

FastAPI does not replace the database, business logic, or authentication design. It coordinates those pieces at the HTTP boundary.

## 2. A request through the layers

A registration request travels through the code like this:

```text
POST /auth/register
        ↓
route: HTTP status and error translation
        ↓
schema: validate name, email, and password
        ↓
service: enforce patient-only registration and hash password
        ↓
repository: query and create a User
        ↓
SQLAlchemy session → PostgreSQL
```

- **Route:** understands HTTP: request bodies, cookies, headers, response models, and status codes.
- **Schema:** defines which fields can enter or leave the API. `UserPublic` deliberately has no password field.
- **Service:** owns business rules such as authentication and patient-only public registration.
- **Repository:** contains database reads and writes for users.
- **Model:** maps the Python `User` class to the `users` table.

Not every one-line query needs a new abstraction. These layers exist where they make ownership clearer and keep later feature growth manageable.

## 3. Authentication versus authorization

**Authentication** answers “Who are you?” Login verifies an email/password pair, and later requests prove identity with a signed access token.

**Authorization** answers “Are you allowed to do this?” After identity is established, role dependencies compare the current user's database role with the roles allowed for a route.

A valid patient token authenticates the patient, but it does not authorize that patient to open a doctor-only route. That request receives `403 Forbidden`. Missing or invalid identity receives `401 Unauthorized`.

## 4. Password hashing

Passwords are processed with Argon2, a deliberately expensive password-hashing algorithm. A random salt is incorporated automatically, so identical passwords normally produce different hashes. Login does not decrypt a hash—there is nothing to decrypt. The hashing library evaluates the submitted password against the stored hash.

The application stores only `password_hash`. Response schemas never include it. If the database is exposed, hashing increases the time and cost needed to guess passwords, although weak passwords can still be guessed. That is why input validation requires at least 10 characters with upper case, lower case, and a number.

## 5. JWT access and refresh tokens

A JWT consists of encoded claims plus a signature. CareLoop tokens include:

- `sub`: the user's UUID
- `role`: the role at issuance time
- `token_type`: `access` or `refresh`
- `iat`: issued-at time
- `exp`: expiration time

The signature lets the backend detect alteration; it does not encrypt the claims. Never put secrets in JWT claims.

The access token lasts 15 minutes by default. React keeps it in memory and sends it in the `Authorization: Bearer ...` header. The refresh token lasts seven days by default and is stored in an HTTP-only cookie, so frontend JavaScript cannot read it. The refresh endpoint validates it, reloads the active user and current role from the database, rotates the refresh cookie, and returns a new access token.

Token types are checked explicitly. A refresh token cannot authorize `/me`, and an access token cannot call `/refresh`. Logout clears the cookie. A later production-hardening phase should store refresh-session identifiers server-side for targeted revocation and reuse detection.

## 6. Role-based dependencies

`get_current_user` performs the shared authentication sequence:

1. Read the Bearer token.
2. verify its signature, required claims, type, and expiry.
3. Load the user by UUID.
4. Require an active account.
5. Ensure the token's role still matches the database role.

`require_roles(...)` builds on that dependency. It receives the already authenticated user and returns `403` when the role is not allowed. Routes declare policy close to the endpoint, for example `Depends(require_roles(UserRole.ADMIN))`, without duplicating token logic.

Frontend route guards improve navigation but are not security boundaries. A user can change browser code. Backend role checks are authoritative.

## 7. Why registration cannot choose doctor or admin

The registration request schema has only `full_name`, `email`, and `password`; it has no `role` field. More importantly, the service passes `UserRole.PATIENT` itself. A caller cannot create a privileged account by adding `"role": "admin"` to JSON.

Administrators are bootstrapped through a local command that requires environment variables and direct database access. It is not an HTTP endpoint. Future doctor creation should require an authenticated administrator workflow and an audit trail.

## 8. SQLAlchemy sessions

A SQLAlchemy `Session` is a unit of work, not the database itself. It tracks loaded and changed objects and uses a pooled database connection when required.

The FastAPI dependency creates one session per request. If the request finishes, it commits. If code raises an exception, it rolls back so partial work does not remain. It always closes the session, returning its connection to the pool. Repository methods use the supplied session rather than creating their own, so one future operation can update several tables atomically.

Registration calls `flush` before returning. Flush sends the pending insert inside the current transaction and surfaces a database uniqueness conflict early. The request dependency still owns the final commit.

## 9. Alembic migrations

SQLAlchemy models describe the schema the code expects today. Alembic migration files describe how to move a real database between schema versions without dropping all data.

The initial migration creates the enum and `users` table. `alembic upgrade head` applies pending migrations and records the current revision. Autogeneration compares model metadata with the database, but generated migrations must always be reviewed: tools cannot infer every rename, data migration, locking concern, or safe deployment sequence.

Model changes and migration changes belong together. Running `Base.metadata.create_all()` is acceptable for isolated tests, but it is not a replacement for versioned migrations in deployed environments.

## 10. Interview checklist

You should be able to explain:

1. Why public input and public output use different schemas.
2. Why email normalization exists in both validation and database access, while uniqueness is ultimately enforced by PostgreSQL.
3. Why password hashing is one-way and why Argon2 is appropriate.
4. Why access and refresh tokens have different lifetimes, storage, and accepted endpoints.
5. Why a frontend protected route is convenience while backend authorization is security.
6. How one request-scoped SQLAlchemy session enables rollback and future multi-table transactions.
7. Why the service chooses the patient role rather than trusting a registration payload.
8. What `401`, `403`, `409`, and `422` mean in this API.
9. Why migrations are reviewed artifacts instead of startup-time table creation.
10. Where future doctor, appointment, summary, and notification modules fit without turning the system into microservices.

One useful way to practice is to trace registration, login, `/me`, and refresh from the browser through every backend layer, naming both the data and security decision at each step.

