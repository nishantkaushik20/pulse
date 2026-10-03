# Database

The data model for Pulse is recorded in this document.

Multi-tenancy constraints:

- Every tenant-owned resource must contain `tenant_id`.
- Never accept `tenant_id` from the client as authoritative.
- Resolve tenant from authenticated context.
- Every repository query must enforce tenant scope.
