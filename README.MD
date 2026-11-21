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
| External services | Google Calendar, Gmail, Microsoft Graph, Claude, Gemini      |

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
    integrations/  google, microsoft, llm, anthropic, gemini
    worker/        Celery app and tasks
  alembic/         database migrations
  tests/
frontend/
  src/
    routes/        React Router configuration
    modules/       today, dashboard (agenda, inbox, tasks), chat, admin
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

## Deployment

Production runs with `docker-compose.prod.yml` (Caddy serves the built frontend and proxies
`/api` to the backend) behind Cloudflare. See [deploy/README.md](deploy/README.md).

## Authentication

Users register and sign in with email and password (`/auth/register`, `/auth/login`,
`/auth/logout`, `/auth/me`). The session is a JWT stored in an `httpOnly` cookie. Accounts have
a role (`user` or `admin`) and can be disabled by setting `is_active` to false.

## Google Calendar and Gmail

Each user connects one or more Google accounts from the "Cuentas conectadas" page
(OAuth 2.0 authorization code flow, read-only `calendar.readonly` and `gmail.readonly`
scopes). Tokens are stored encrypted with AES-256-GCM; events and emails are never stored and
are read from Google on demand (`/calendar/events`, `/mail/messages`).

The "Bandeja" page shows the latest inbox messages of every connected account, and the assistant can
list and read them. Accounts connected before the mail permission existed keep their calendar
and show "Falta permiso de correo" until the user connects them again. Email text is written
by third parties, so the assistant treats it as data: after it reads mail, every action of that
instruction waits for the user's confirmation, even in automatic mode.

Setup in Google Cloud Console:

1. Create a project and enable the Google Calendar API and the Gmail API.
2. Configure the OAuth consent screen (external, testing), add the `calendar.readonly` and
   `gmail.readonly` scopes and add the test users.
3. Create an OAuth client of type "Web application" with the redirect URI
   `http://localhost:8000/integrations/google/callback`.
4. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and `TOKEN_ENCRYPTION_KEY` in `.env`, then
   restart the backend.

## Tasks

The internal task manager has its own page ("Tareas"); the "Hoy" page combines today's
meetings, urgent tasks and unread mail. Each user creates, edits,
completes, reopens and deletes their own tasks (`/tasks`); every operation is recorded in the
audit log.

## Assistant chat

Each user chooses the model of the assistant in "Configuración" and stores their own API key
for its provider: Claude (Anthropic, official `anthropic` SDK) or Gemini (Google, official
`google-genai` SDK). Keys are verified with the provider and stored encrypted with
AES-256-GCM. Both providers sit behind a common session interface
(`app/integrations/llm`), so the assistant logic is the same for either. Replies are streamed
as Server-Sent Events.

The model never changes data directly: it proposes actions through strict tools (list, create,
edit, complete and delete tasks; read the calendar). Every proposed action is validated against
its format before running. Depending on the user's execution mode, actions that modify data
wait for confirmation or run immediately; deleting a task always asks for confirmation. Each
instruction is stored as an interaction with its proposed actions and their outcome.

Users can also write their own instructions in "Configuración" (up to 2000 characters) on how
the assistant should answer and summarise their tasks and calendars. The text is added to the
system prompt of either provider as style preferences: it changes tone, length, order and
language, but not the rules above.

## Administration

The `/admin` view is restricted to the `admin` role. It lists accounts, creates regular accounts and enables or disables
them (`/admin/users`), and shows the audit log (`/admin/audit-logs`), which records account
registration, sign-in, sign-out, account status changes and account connections. The
connections tab shows the status of every user's connected accounts, never their tokens.

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
