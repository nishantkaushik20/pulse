# Architecture

Pulse is a multi-tenant SaaS platform. This document records the identity and domain foundation that exists today.

## Applications

- `apps/api` is a Python FastAPI service. Configuration uses Pydantic settings. Persistence uses SQLAlchemy 2 and Alembic against PostgreSQL. Readiness checks Redis. Logs are structured JSON on stdout.
- `apps/web` is a Next.js TypeScript application. It does not authenticate users yet.
- `packages/domain`, `packages/ai`, and `packages/integrations` are reserved and empty.
- `workers` is reserved and empty. Background workflows are not part of this phase.

## Local infrastructure

Docker Compose runs PostgreSQL, Redis, the API, and the web app. Copy `.env.example` to `.env` for host-side configuration. Compose overrides database and Redis hosts so the API container uses the service names.

Clerk is optional outside production. Set `CLERK_ISSUER` and `CLERK_SECRET_KEY` when authenticated routes should accept real Clerk session tokens. `APP_ENV=production` refuses to start without both.

## HTTP

- `GET /health` is liveness. It reports that the process can serve requests and does not check PostgreSQL or Redis. Docker Compose uses this probe. The API listens only after migrations finish, so a healthy probe means the process is up.
- `GET /ready` is dependency readiness. It checks PostgreSQL and Redis. A failed dependency returns HTTP 503 and a generic check status. Connection details stay out of the response and the logs.

Authenticated routes are listed under API. They return 401 when the caller has no valid Clerk session. They do not accept a development bypass.

## Authentication

Pulse does not implement passwords. Clerk verifies the session. Pulse stores the internal user and decides authorization.

1. The client sends `Authorization: Bearer <Clerk session JWT>`.
2. The API verifies the JWT with Clerk's JWKS (`CLERK_JWKS_URL`, or `{CLERK_ISSUER}/.well-known/jwks.json`) using RS256. The `iss`, `exp`, and `sub` claims are required. `sub` is the Clerk user id.
3. Email and name are taken from the token when present. If email is missing, the API loads the Clerk user with `CLERK_SECRET_KEY` and does not log that response.
4. Pulse inserts an internal `users` row on first sight of that Clerk id.
5. The current tenant is the user's earliest `tenant_users` membership.

There is no `AUTH_DISABLED` switch and no second authenticator in the application. Tests replace the `get_identity` dependency in the test process only. Unset Clerk configuration makes authenticated routes return 401. `/health` stays available.

The API does not log bearer tokens, authorization headers, Clerk payloads, or customer phone numbers.

## Tenant resolution

Tenant id is never read from a body field, query parameter, or header.

`POST /tenants` creates a tenant only when the caller has no membership, and the caller becomes `OWNER`. A later request resolves that membership. A user who already belongs to a tenant receives 409 from `POST /tenants`. Switching among multiple memberships is not implemented. The active tenant is the earliest membership by `created_at`, then `id`.

## Authorization

Roles are `OWNER` and `MEMBER`.

- `OWNER` can rename the tenant and add members.
- `MEMBER` can read membership and use the business record APIs.
- A caller with no membership receives 403 on tenant-owned routes.

There are no finer permissions in this phase.

## Tenant isolation

Every tenant-owned table includes `tenant_id`. `action_approvals` includes it so approval queries do not depend on joining through `actions`.

Tenant-owned reads and writes go through repositories constructed with the tenant id from `TenantContext`. Those repositories add `tenant_id` to every select, update, and delete. Inserts overwrite `tenant_id` with the repository tenant, including when a row was built with a different value. Missing rows in another tenant return 404, including when the caller knows the other tenant's id.

`users` is global. Membership lookups use the authenticated Pulse user id.

Polymorphic `entity_id` columns are not foreign keys. A later reader must still scope by `tenant_id` and must not treat `entity_id` as permission to load another tenant's row.

## Repository pattern

Services in `pulse_api.services` are the application boundary. Routes depend on services. Services depend on repositories and the request's `TenantContext`. Repositories are the only place that query tenant-owned tables.

SQLAlchemy sessions are not returned to routes and must not be given to a future AI or tool layer. Tools, when they exist, will call typed services that already carry the tenant context.

## API

- `GET /me` returns the Pulse user and current tenant.
- `POST /tenants` bootstraps the caller's first tenant.
- `GET /tenant` and `PATCH /tenant` read and rename the current tenant. Rename requires `OWNER`.
- `GET /tenant/members` and `POST /tenant/members` list members and add one. Adding a member requires `OWNER`.
- Customers: `GET/POST /customers`, `GET/PATCH/DELETE /customers/{id}`.
- Contacts: `GET/POST /customers/{id}/contacts`, `GET/PATCH/DELETE /contacts/{id}`.
- Attention items: `GET/POST /attention-items`, `GET /attention-items/{id}`.
- Business events: `GET/POST /business-events`, `GET /business-events/{id}`.
- Actions: `GET/POST /actions`, `GET /actions/{id}`.
- Approvals: `GET/POST /actions/{id}/approvals`, `GET /actions/{id}/approvals/{approval_id}`.

Created actions are `PENDING`. Created attention items are `OPEN`. Approval does not execute the action.

## Intentionally not implemented

Gmail, WhatsApp, AI, LLM calls, agents, RAG, vector search, background workers, business integrations, invoices, payments, CRM pipelines, dashboards, attention ranking, and action execution are out of scope. The web app does not call these APIs yet.

## Constraints

- Read `docs/` before implementing.
- Do not invent architecture.
- Prefer existing abstractions.
- Keep changes scoped to the requested task.
- Do not add dependencies without justification.
