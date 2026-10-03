# Pulse

Multi-tenant SaaS foundation for SMB business operations.

```
apps/api     FastAPI, SQLAlchemy 2, Alembic, Pydantic
apps/web     Next.js, TypeScript
packages/    reserved
workers/     reserved
tests/       unit, integration, security, e2e
```

Read `docs/` and `AGENTS.md` before implementing.

## Local API

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e "apps/api[dev]"
cp .env.example .env
pytest
ruff check
mypy
uvicorn pulse_api.main:app --reload --app-dir apps/api/src
```

## Local web

```bash
cd apps/web
npm ci
npm test
npm run lint
npm run typecheck
npm run dev
```

## Docker Compose

```bash
docker compose up --build
```

- API: http://localhost:8000/health
- Web: http://localhost:3000

Authenticated routes require a Clerk session token. Leave Clerk unset locally and those routes return 401. `APP_ENV=production` requires `CLERK_ISSUER` and `CLERK_SECRET_KEY`. See `docs/architecture.md`.

Do not commit `.env`.
