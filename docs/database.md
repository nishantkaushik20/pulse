# Database

PostgreSQL is the application database. The API uses SQLAlchemy 2 and Alembic.

Migrations:

- `0001_baseline` is empty.
- `0002_domain` creates the identity and tenant-owned tables below.
- `0003_gmail` creates `gmail_connections`, `message_threads`, and `messages`.
- `0004_attention` adds the unique attention-item source index.
- `0005_context` adds attention resolution metadata and a derived exact-email match.
- `0006_ai` creates `ai_runs` for model name, token estimates, latency, and status. It does not store prompts or message bodies.

Primary keys are UUIDs. PostgreSQL generates them with `gen_random_uuid()`. The ORM also assigns UUIDs on the client so tests can use SQLite.

## Identity

`users` is not tenant-owned.

| Column | Notes |
| --- | --- |
| id | UUID primary key |
| clerk_user_id | unique |
| email | indexed, not unique |
| name | |
| created_at, updated_at | |

`tenants` stores `id`, `name`, `created_at`, and `updated_at`. There is no tenant delete API.

`tenant_users` stores `id`, `tenant_id`, `user_id`, `role`, and `created_at`.

- Unique `(tenant_id, user_id)`.
- `role` is `OWNER` or `MEMBER`.
- Indexed by `user_id` for membership lookup.

## Tenant-owned records

`customers`: `tenant_id`, `name`, `company_name`, `email`, `phone`, `status` (`ACTIVE` or `ARCHIVED`), timestamps. Indexed by `tenant_id` and `(tenant_id, email)`.

`contacts`: `tenant_id`, `customer_id`, `name`, `email`, `phone`, timestamps. Indexed by `tenant_id` and `(tenant_id, customer_id)`.

`business_events`: `tenant_id`, `event_type`, `entity_type`, `entity_id`, `source`, `occurred_at`, `data`, `created_at`. `data` is JSONB. Indexed by `(tenant_id, occurred_at)`. `entity_id` is not a foreign key.

`attention_items`: `tenant_id`, `type`, `priority` (`LOW`, `MEDIUM`, `HIGH`), `title`, `description`, `status` (`OPEN`, `RESOLVED`), `entity_type`, `entity_id`, `due_at`, `resolved_at`, `resolved_by`, `dismiss_reason` (`not_relevant`, `done`, or `waiting`), `matched_customer_id`, `match_method` (`exact_email`), timestamps. Indexed by `(tenant_id, status)`. Unique `(tenant_id, type, entity_type, entity_id)`. `entity_id` is not a foreign key. `matched_customer_id` references `customers` with `ON DELETE SET NULL` because the match is derived. `resolved_by` references `users`. Rows with a null entity are not collapsed by that unique index, because SQL treats those nulls as distinct. The `email_review` rule uses the unique key so one message produces one attention item. Public `POST /attention-items` and `POST /business-events` do not create rows. Resolving an item updates `status` to `RESOLVED` and keeps the row. It does not insert another item and does not change the unique key.

`actions`: `tenant_id`, `action_type`, `status` (`PENDING`, `COMPLETED`, `CANCELLED`), `requested_by`, `entity_type`, `entity_id`, `input`, `result`, `created_at`, `completed_at`. `input` and `result` are JSONB. Indexed by `(tenant_id, status)`. `entity_id` is not a foreign key. This table records an action request. It does not execute one.

`action_approvals`: `tenant_id`, `action_id`, `approved_by`, `status` (`APPROVED` or `REJECTED`), `approved_at`, `created_at`. Indexed by `tenant_id` and `action_id`. `tenant_id` is stored on the approval so a query cannot omit tenant scope by joining through another table.

JSON values are objects and are limited to 16KB at the API boundary. There is no separate document store.

## Relationships and deletes

Foreign keys use `ON DELETE RESTRICT`.

- `tenant_users.tenant_id` and every tenant-owned `tenant_id` reference `tenants`.
- `tenant_users.user_id`, `actions.requested_by`, and `action_approvals.approved_by` reference `users`.
- `contacts.customer_id` references `customers`. The service rejects customer deletion while contacts exist.
- `action_approvals.action_id` references `actions`.
- `gmail_connections.connected_by` references `users`.
- `messages.thread_id` references `message_threads`.

Deleting a tenant, user, customer, action, Gmail connection, or message thread that is still referenced fails in the database. Cascades are not used. Disconnecting Gmail clears credential columns and keeps the connection row and ingested messages. Polymorphic `entity_id` values are intentionally not foreign keys, so they do not delete or restrict anything. Readers must filter those rows by `tenant_id`.

## Gmail

`gmail_connections` is tenant-owned.

| Column | Notes |
| --- | --- |
| id | UUID primary key |
| tenant_id | required, `ON DELETE RESTRICT` |
| connected_by | user who completed OAuth |
| external_account_id | mailbox address from `users.getProfile`, stored lowercase |
| status | `ACTIVE`, `REVOKED`, or `ERROR` |
| encrypted_refresh_token, encrypted_access_token | AES-256-GCM payload (`nonce \|\| ciphertext/tag`), nullable |
| access_token_expires_at | |
| encryption_key_version | |
| history_id | stored for a later incremental sync; not used by Phase 3 |
| last_synced_at, last_error_code | |
| scopes | granted scope string |
| created_at, updated_at | |

Unique `(tenant_id, external_account_id)` and unique `external_account_id`. A mailbox connected to another tenant is a generic conflict. The response does not include the other tenant. Reconnecting the same mailbox in the same tenant updates the row. Plaintext OAuth tokens are not columns.

`message_threads`: `tenant_id`, `source` (`gmail`), `external_thread_id`, `subject`, timestamps. Unique `(tenant_id, source, external_thread_id)`.

`messages`: `tenant_id`, `thread_id`, `source` (`gmail`), `external_message_id`, `from_email`, `from_name`, `to_addresses`, `cc_addresses`, `subject`, `snippet`, `body_text`, `received_at`, `created_at`. Unique `(tenant_id, source, external_message_id)`. Address lists are JSONB. `body_text` is plain text capped at 32,768 characters. There is no HTML body and no attachment table.

Ingestion inserts with `ON CONFLICT DO NOTHING` on that message key. The `EMAIL_RECEIVED` event is written in the same transaction only when the insert stores a new row. `event.data` contains `provider`, `external_message_id`, and `external_thread_id`.

## Multi-tenancy

- Every tenant-owned resource contains `tenant_id`.
- Never accept `tenant_id` from the client as authoritative.
- Resolve tenant from authenticated context.
- Every repository query must enforce tenant scope.
