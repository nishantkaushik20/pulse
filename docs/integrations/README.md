# Integrations

Per-integration documentation lives in this directory.

New integrations require integration tests.

## Gmail

Phase 3 connects one mailbox and ingests a bounded inbox page into `message_threads` and `messages`.

### OAuth

`POST /integrations/gmail/connect` is called by an authenticated owner. Pulse generates `state` and a PKCE S256 verifier, stores them in Redis under `oauth_state:{state}` for 10 minutes, and returns Google's authorization URL.

Google redirects to `GET /integrations/gmail/callback?code&state`. The callback does not use a Clerk session. It consumes the Redis value once, exchanges the code with the stored verifier and `GOOGLE_CLIENT_SECRET`, and reads the mailbox from `users.getProfile`. The connection is stored for the tenant that was in Redis. The browser is then sent to `WEB_APP_URL` with either `?gmail=connected` or `?gmail=error&reason=invalid_state|denied|failed|conflict`. The redirect does not include `code` or `state`.

`state` is a bearer secret. It cannot be retargeted by adding `tenant_id` or `user_id` to the callback.

### Scope

The only requested scope is `https://www.googleapis.com/auth/gmail.readonly`.

`gmail.readonly` is a restricted Google scope. Because Pulse stores Gmail message data on the server, a public production deployment requires Google's OAuth verification and the applicable security assessment. This implementation does not request `gmail.send`, `gmail.modify`, `gmail.compose`, `mail.google.com`, or `gmail.metadata`, and it does not try to avoid that review.

### Credentials

`INTEGRATION_ENCRYPTION_KEY` is a base64-encoded 32-byte key. Tokens are stored as AES-256-GCM `nonce || ciphertext/tag` plus `encryption_key_version`. PostgreSQL does not store plaintext tokens. Production startup fails when the key is absent. Local Gmail routes return 503 instead.

Disconnect keeps the `gmail_connections` row, sets `REVOKED`, clears token columns, and best-effort revokes the refresh token at Google. Ingested messages stay.

### Sync

`POST /integrations/gmail/connections/{id}/sync` is manual. The first implementation loads at most 50 messages matching `in:inbox newer_than:7d -in:sent`, then drops resources that are not inbox mail. Sent mail is not stored as `EMAIL_RECEIVED`.

The same Gmail id in one tenant inserts one Pulse message and one `EMAIL_RECEIVED` event. A second sync does not insert either again. Event data is `provider`, `external_message_id`, and `external_thread_id`.

Plain text is kept up to 32,768 characters. HTML and attachments are discarded. Bodies are not logged.

Access tokens are refreshed when missing or expiring within 60 seconds. `invalid_grant` revokes the connection and stops. 429 and 5xx return 503 without moving `last_synced_at`. A malformed message stops the page. Messages already committed on that sync remain. There is no background retry.

`history_id` may be saved from `users.getProfile` after a successful page. Phase 3 does not implement `history.list` incremental sync. A later phase can add that.

### Tests

Gmail tests use a fake client and an in-memory state store. CI does not call Google.
