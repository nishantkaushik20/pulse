# Actions

External actions for Pulse are recorded in this document.

The `actions` and `action_approvals` tables record a request and an approval decision. `POST /actions/{id}/execute` runs only `create_reminder` and an approved `store_draft`. Sending mail, payments, and other types are refused. The same idempotency key does not apply a completed action twice. `audit_logs` stores the actor, action type, target, and result code, not the draft text.

Constraints for later execution:

- Actions must be idempotent.
- External actions require audit logs.
- Financial actions require explicit approval.
