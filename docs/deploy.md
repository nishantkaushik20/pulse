# Deploy

Use two environments, staging and production. The web app is a Next.js service. The API, PostgreSQL, and Redis run together. Vercel fits the web app. Railway or Render fits the API, PostgreSQL 16, and Redis.

## Secrets

Set these in the host, not in the repository:

- `APP_ENV=production` on the API. Production refuses to start without `CLERK_ISSUER`, `CLERK_SECRET_KEY`, and `INTEGRATION_ENCRYPTION_KEY`.
- `DATABASE_URL` as `postgresql+psycopg://...` and `REDIS_URL`.
- `WEB_APP_URL` as the public https origin of that environment. CORS allows that origin only.
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY`. Clerk authorized origins must match `WEB_APP_URL`.
- `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, and `GOOGLE_OAUTH_REDIRECT_URI`. The redirect URI is `{API_ORIGIN}/integrations/gmail/callback`.
- `INTEGRATION_ENCRYPTION_KEY` is a distinct 32-byte key per environment.
- `AI_MODEL=none` until a provider is chosen. `AI_DAILY_BUDGET` stays at 20 unless a review changes it.

Apply migrations with `alembic upgrade head` from `apps/api` before serving traffic. CI runs that command against PostgreSQL 16.

Do not add an authentication bypass for staging. Do not send Gmail until the Google app is verified for the scopes you request. The current scope is `gmail.readonly`.
