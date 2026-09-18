# LifeLink API

LifeLink is a blood-donation coordination platform. The backend is a modular FastAPI
application backed by PostgreSQL. Supabase is not used.

## Phase 1 status

The first Phase 1 foundation includes:

- combined user identity and password credentials
- Argon2id password hashing
- email OTP on every Super Admin login
- opaque server-side sessions stored as hashes
- local console and SMTP email-delivery adapters
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

The application intentionally has no built-in database password or OTP pepper. Add
the required values to `.env`. Generate the OTP pepper with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

For local development, the minimum configuration is:

```env
DATABASE_URL=postgresql+psycopg://lifelink:lifelink@localhost:5432/lifelink
OTP_PEPPER=paste-the-generated-random-value-here
OTP_MODE=fixed
FIXED_OTP_CODE=123456
FRONTEND_URL=http://localhost:3000
API_PUBLIC_URL=http://127.0.0.1:8000
EMAIL_BACKEND=console
COOKIE_SECURE=false
```

Fixed OTP mode and the console adapter are for development or test staging only.
Production rejects fixed OTP and console delivery at startup.

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

1. `POST /api/v1/auth/login` validates the password and emails an OTP for Super Admins.
2. `POST /api/v1/auth/otp/verify` consumes the OTP and creates a server-side session.
3. The browser receives only an opaque `lifelink_session` HttpOnly cookie.
4. `GET /api/v1/auth/session` loads current identity from the database session.
5. `POST /api/v1/auth/logout` revokes the database session and removes the cookie.

For production, deploy the frontend and API on sibling domains such as
`app.lifelink.com` and `api.lifelink.com`, set `COOKIE_SECURE=true`, and configure
`FRONTEND_URL` to the exact frontend origin. Frontend requests must include credentials.
