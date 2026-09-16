# LifeLink API

LifeLink is a blood-donation coordination platform. The backend is a modular FastAPI
application backed by PostgreSQL. Supabase is not used.

## Phase 1 status

The first Phase 1 foundation includes:

- combined user identity and password credentials
- Argon2id password hashing
- mandatory TOTP enrollment during the first Super Admin login
- short-lived JWT access tokens
- rotating refresh tokens stored as hashes in database sessions
- logout, logout-all, session listing, and account-state enforcement
- platform roles and permissions schema
- security audit-log schema and authentication events
- Alembic migrations
- a secure command for bootstrapping a Super Admin

Hospital, community, invitation, user-administration, and audit-reading APIs are the
next Phase 1 vertical slices.

## Local setup

Requirements:

- Python 3.12 or newer
- Docker with Compose, or a PostgreSQL 16+ instance

Create an environment and install the dependencies:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env`. The application intentionally has no built-in database
password, JWT secret, or MFA encryption key; it will refuse to start until they are
provided through the environment. Generate an MFA encryption key with:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Generate a separate random `JWT_SECRET` of at least 32 bytes. Never reuse the MFA
encryption key as the JWT secret.

Start PostgreSQL and migrate the database:

```powershell
docker compose up -d postgres
alembic upgrade head
```

Create the first Super Admin:

```powershell
python scripts/create_super_admin.py `
  --email admin@example.com `
  --first-name LifeLink `
  --last-name Admin
```

Start the API:

```powershell
uvicorn app.main:app --reload
```

API documentation is available at `http://localhost:8000/docs`.

## Authentication flow

1. `POST /api/v1/auth/login` validates email and password and returns an MFA challenge.
2. On first login, `POST /api/v1/auth/mfa/setup` returns a TOTP provisioning URI.
3. `POST /api/v1/auth/mfa/verify` verifies the code, returns an access token, and sets
   the rotating refresh token as an HttpOnly cookie.
   The one-time recovery codes returned after enrollment can be used through
   `POST /api/v1/auth/mfa/recover`.
4. The frontend sends the access token as `Authorization: Bearer <token>`.
5. `POST /api/v1/auth/refresh` rotates the refresh token and returns a new access token.

For production, deploy the frontend and API on sibling domains such as
`app.lifelink.com` and `api.lifelink.com`, set `COOKIE_SECURE=true`, and configure
`FRONTEND_URL` to the exact frontend origin.
