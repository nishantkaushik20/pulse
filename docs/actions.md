# Actions

External actions for Pulse are recorded in this document.

The `actions` and `action_approvals` tables record a request and an approval decision. They do not execute external work, enforce idempotency, or write an audit log beyond the row itself.

Constraints for later execution:

- Actions must be idempotent.
- External actions require audit logs.
- Financial actions require explicit approval.
