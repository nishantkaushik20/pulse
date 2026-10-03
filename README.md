# Pulse

Monorepo layout:

```
pulse/
├── apps/
│   ├── api/
│   └── web/
├── packages/
│   ├── domain/
│   ├── ai/
│   └── integrations/
├── workers/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── security/
│   └── e2e/
├── docs/
│   ├── product.md
│   ├── architecture.md
│   ├── database.md
│   ├── security.md
│   ├── ai.md
│   ├── actions.md
│   └── integrations/
├── infra/
├── AGENTS.md
├── README.md
├── docker-compose.yml
└── .env.example
```

Read `docs/` and `AGENTS.md` before implementing. Copy `.env.example` to `.env` for local configuration. Do not commit `.env`.
