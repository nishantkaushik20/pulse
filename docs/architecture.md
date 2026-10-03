# Architecture

Pulse is a multi-tenant SaaS platform. This document records the foundation that exists today.

## Applications

- `apps/api` is a Python FastAPI service. Configuration uses Pydantic settings. Persistence uses SQLAlchemy 2 and Alembic against PostgreSQL. Readiness checks Redis. Logs are structured JSON on stdout.
- `apps/web` is a Next.js TypeScript application.
- `packages/domain`, `packages/ai`, and `packages/integrations` are reserved and empty.
- `workers` is reserved and empty. Background workflows are not part of the foundation.

## Local infrastructure

Docker Compose runs PostgreSQL, Redis, the API, and the web app. Copy `.env.example` to `.env` for host-side configuration. Compose overrides database and Redis hosts so the API container uses the service names.

## HTTP

- `GET /health` is liveness. It reports that the process can serve requests and does not check PostgreSQL or Redis. Docker Compose uses this probe. The API listens only after migrations finish, so a healthy probe means the process is up.
- `GET /ready` is dependency readiness. It checks PostgreSQL and Redis. A failed dependency returns HTTP 503 and a generic check status. Connection details stay out of the response and the logs.

## Multi-tenancy

No tenant-owned tables exist yet. When they are added, every tenant-owned resource contains `tenant_id`, tenant identity comes from the authenticated context, and repository queries enforce tenant scope. The API does not accept `tenant_id` from the client.

## Constraints

- Read `docs/` before implementing.
- Do not invent architecture.
- Prefer existing abstractions.
- Keep changes scoped to the requested task.
- Do not add dependencies without justification.
