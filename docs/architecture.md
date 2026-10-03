# Architecture

Pulse is a multi-tenant SaaS platform. This document records the identity and domain foundation that exists today.

## Applications

- `apps/api` is a Python FastAPI service. Configuration uses Pydantic settings. Persistence uses SQLAlchemy 2 and Alembic against PostgreSQL. Readiness checks Redis. Logs are structured JSON on stdout.
- `apps/web` is a Next.js TypeScript application. It does not authenticate users yet.
- `packages/domain`, `packages/ai`, and `packages/integrations` are reserved and empty.
- `workers` is reserved and empty. Background workflows are not part of this phase.

## Local infrastructure

Docker Compose runs PostgreSQL, Redis, the API, and the web app. Copy `.env.example` to `.env` for host-side configuration. Compose overrides database and Redis hosts so the API container uses the service names.

Clerk is optional outside production. Set `CLERK_ISSUER` and `CLERK_SECRET_KEY` when authenticated routes should accept real Clerk session tokens. `APP_ENV=production` refuses to start without both, and without `INTEGRATION_ENCRYPTION_KEY`.

Gmail OAuth client id, client secret, and redirect URI are not startup requirements. When any of them or the encryption key is missing, Gmail routes return 503. `/health` and `/ready` stay available.

## HTTP

- `GET /health` is liveness. It reports that the process can serve requests and does not check PostgreSQL or Redis. Docker Compose uses this probe. The API listens only after migrations finish, so a healthy probe means the process is up.
- `GET /ready` is dependency readiness. It checks PostgreSQL and Redis. A failed dependency returns HTTP 503 and a generic check status. Connection details stay out of the response and the logs.

Authenticated routes are listed under API. They return 401 when the caller has no valid Clerk session. They do not accept a development bypass.

## Authentication

Pulse does not implement passwords. Clerk verifies the session. Pulse stores the internal user and decides authorization.

1. The client sends `Authorization: Bearer <Clerk session JWT>`.
2. The API verifies the JWT with Clerk's JWKS (`CLERK_JWKS_URL`, or `{CLERK_ISSUER}/.well-known/jwks.json`). The signing key is the JWKS key whose `kid` matches the token header. The algorithm must be RS256. `iss` must equal `CLERK_ISSUER`. `exp` is required and must be in the future. `sub` is required and must be a non-empty string. `nbf` and `iat` are checked when the token includes them.
3. Email and name are taken from the token when present. If email is missing, the API loads the Clerk user with `CLERK_SECRET_KEY` and does not log that response.
4. Pulse inserts an internal `users` row on first sight of that Clerk id.
5. `resolve_current_tenant` builds the `TenantContext` for that user.

Trusted for authentication: the RS256 signature, `iss`, `exp`, and `sub`. `nbf` and `iat` are time checks when present.

Not trusted for authorization: `aud`, `azp`, `org_id`, `org_role`, `sid`, email, and name. Pulse has no configured audience and no authorized-party list. Default Clerk session tokens do not require `aud`. A present `aud` or `azp` does not select a tenant or a role. Email and name are profile fields only. Role and tenant come from `tenant_users`.

There is no `AUTH_DISABLED` switch and no second authenticator in the application. Tests replace the `get_identity` dependency in the test process only. Unset Clerk configuration makes authenticated routes return 401. `/health` stays available.

The API does not log bearer tokens, authorization headers, Clerk payloads, or customer phone numbers.

## Tenant resolution

Phase 2 supports one implicit current tenant. `resolve_current_tenant` is the only membership-resolution rule. It returns a `TenantContext` for the earliest membership by `created_at`, then `id`. Services and repositories consume that `TenantContext`. They do not repeat the ordering rule.

Tenant identity must never come from arbitrary client input. It is not read from a body field, query parameter, or header.

`POST /tenants` creates a tenant only when the caller has no membership, and the caller becomes `OWNER`. A later request resolves that membership. A user who already belongs to a tenant receives 409 from `POST /tenants`.

Future tenant switching must verify membership before changing `TenantContext`. This phase does not implement switching or a tenant selector.

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
- Gmail: `POST /integrations/gmail/connect`, `GET /integrations/gmail/callback`, `GET /integrations/gmail/connections`, `POST /integrations/gmail/connections/{id}/disconnect`, `POST /integrations/gmail/connections/{id}/sync`.
- Ingested mail: `GET /messages`, `GET /messages/{id}`, `GET /message-threads`, `GET /message-threads/{id}`.

Created actions are `PENDING`. Created attention items are `OPEN`. Approval does not execute the action.

`OWNER` can connect and disconnect Gmail. `MEMBER` can read ingested mail and trigger a manual sync. There are no finer Gmail permissions.

## Gmail ingestion

Phase 3 connects one Gmail mailbox and manually ingests a bounded inbox page. The web app does not implement a Gmail screen. The callback redirects to `WEB_APP_URL` with `?gmail=connected` or `?gmail=error&reason=`.

1. An authenticated `OWNER` calls `POST /integrations/gmail/connect`.
2. Pulse resolves `TenantContext`, generates an opaque `state` and a PKCE verifier, and stores `oauth_state:{state}` in Redis for 10 minutes. The value is `user_id`, `tenant_id`, and `pkce_verifier`. It is not a token.
3. The response is Google's authorization URL. The only scope is `https://www.googleapis.com/auth/gmail.readonly`.
4. Google redirects the browser to `GET /integrations/gmail/callback`. That route does not use Clerk. It consumes the Redis state once, exchanges the code with the stored PKCE verifier and the configured client secret, and loads `users.getProfile`.
5. The mailbox is stored on `gmail_connections` for the tenant recorded in Redis. Tokens are encrypted. The browser is redirected to the web app without `code` or `state`.

The OAuth `state` is a short-lived bearer secret. The callback ignores any tenant or user id in the query string. Possession of `state` completes the original user's connection. It cannot be retargeted at another tenant. A missing, expired, or reused state is rejected.

Manual sync lists at most 50 inbox messages from the last 7 days (`in:inbox newer_than:7d -in:sent`) and skips anything labeled `SENT` or missing `INBOX`. Each new message is one `messages` row and one `EMAIL_RECEIVED` business event in the same transaction. The idempotency key is `(tenant_id, source, external_message_id)`.

`history_id` is stored for a later phase. This phase does not call `history.list` and does not run a polling loop, watch, or worker.

Gmail HTTP lives behind `GmailClient`. Routes do not receive access or refresh tokens. Tests use a fake client. No test calls Google.

Plain-text bodies are capped at 32,768 characters. HTML and attachments are ignored. Message bodies are not logged and are not rendered as HTML.

Each new `EMAIL_RECEIVED` event is passed to the Attention Engine in the same transaction, before that message is committed.

## Attention Engine

```text
Business events
    ↓
Deterministic rules
    ↓
Attention items
```

The engine is a tenant-scoped service. It does not call an LLM, and it does not rank by meaning. Gmail ingestion stays responsible for mail. It emits `EMAIL_RECEIVED`. The engine reads that Pulse event.

Phase 4 has one rule. `EMAIL_RECEIVED` creates one `OPEN` attention item with priority `MEDIUM` and title `New email needs review`. The item points at the Pulse message. Its description may include the sender and subject. It does not include the message body.

The item does not say that a reply is owed. Pulse does not ingest sent mail and does not match customers, so it cannot tell whether someone is waiting, whether the sender is a customer, or whether the mail is urgent. Keyword scans of the subject are not used.

The same source cannot create a second item. `attention_items` is unique on `(tenant_id, type, entity_type, entity_id)` when those values are present. A repeated Gmail sync inserts no message, no event, and no attention item. Evaluating the same event again inserts nothing.

There is no attention-engine HTTP route. Callers read items through the existing attention API. Creation during sync is synchronous. There is no worker, queue, or polling loop.

## Intentionally not implemented

WhatsApp, AI, LLM calls, agents, attention ranking, semantic urgency, automatic replies, Gmail sending, Pub/Sub, Gmail watch, polling, incremental `history.list` sync, vector search, embeddings, RAG, attachment download, customer matching, tenant switching, background workers, invoices, payments, CRM pipelines, dashboards, and action execution are out of scope. The web app does not call these APIs yet.

## Constraints

- Read `docs/` before implementing.
- Do not invent architecture.
- Prefer existing abstractions.
- Keep changes scoped to the requested task.
- Do not add dependencies without justification.
