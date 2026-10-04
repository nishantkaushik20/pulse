# AI

AI behavior for Pulse is recorded in this document.

LLMs cannot directly access the database. `POST /attention/{id}/explain` and `POST /attention/{id}/draft` call a provider interface with a small context packet. The default provider is disabled. Output is one text field. Extra keys are ignored. A daily per-tenant budget is `AI_DAILY_BUDGET`. Runs are logged in `ai_runs` without the prompt or the message body. These routes do not create customers, attention, or actions.

- LLMs cannot directly access the database.
- LLMs interact only through typed tools.
- Tool arguments must be validated.
- AI cannot bypass authorization.
- External actions must pass policy validation.
