# SyncTask

Intelligent personal productivity assistant that centralises calendar, email and task
management across Google and Microsoft, operated through natural language.

## Architecture

Three-layer client-server architecture plus an external services layer.

| Layer             | Technology                                              |
| ----------------- | ------------------------------------------------------- |
| Presentation      | React 18, TypeScript, React Router, Vite                |
| Business          | Python 3.12, FastAPI (MVC), Celery + Redis              |
| Persistence       | PostgreSQL 16, SQLAlchemy, Alembic                      |
| External services | Google Calendar, Gmail, Microsoft Graph, Google Gemini  |

## Project structure

```
backend/
  app/
    core/          settings and security
    db/            SQLAlchemy base and session
    models/        ORM models (Model)
    schemas/       Pydantic schemas (View)
    controllers/   API routers (Controller)
    services/      business logic
    modules/       auth, audit, ai
    integrations/  google, microsoft, gemini
    worker/        Celery app and tasks
  alembic/         database migrations
  tests/
frontend/
  src/
    routes/        React Router configuration
    modules/       chat, dashboard, admin
    services/      HTTP client
    components/    shared components
    types/         shared types
docker-compose.yml backend, worker, db, redis
```

## Getting started

```bash
cp .env.example .env        # then set POSTGRES_PASSWORD and the other secrets
docker compose up --build   # backend on http://localhost:8000 (docs at /docs)
```

```bash
docker compose exec backend alembic upgrade head                 # create the database schema
docker compose exec backend python -m app.scripts.create_admin   # first admin, from ADMIN_EMAIL / ADMIN_PASSWORD
```

```bash
cd frontend
npm install
npm run dev                 # frontend on http://localhost:5173
```

## Authentication

Users register and sign in with email and password (`/auth/register`, `/auth/login`,
`/auth/logout`, `/auth/me`). The session is a JWT stored in an `httpOnly` cookie. Accounts have
a role (`user` or `admin`) and can be disabled by setting `is_active` to false.

## Administration

The `/admin` view is restricted to the `admin` role. It lists accounts and enables or disables
them (`/admin/users`), and shows the audit log (`/admin/audit-logs`), which records account
registration, sign-in, sign-out and account status changes. The OAuth connections tab is a
placeholder until account connection is implemented.

## Development

```bash
# Backend
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .

# Database migrations (inside the backend container)
docker compose exec backend alembic upgrade head

# Frontend
cd frontend
npm run lint && npm run format:check && npm run build
```

## Branching

`main` (stable) ← `develop` (integration) ← `feature/*`
