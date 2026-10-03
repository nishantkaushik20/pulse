# Database

The data model for Pulse is recorded in this document.

## Foundation

PostgreSQL is the application database. The API uses SQLAlchemy 2 and Alembic. The initial migration is a baseline with no tables.

Multi-tenancy constraints:

- Every tenant-owned resource must contain `tenant_id`.
- Never accept `tenant_id` from the client as authoritative.
- Resolve tenant from authenticated context.
- Every repository query must enforce tenant scope.
