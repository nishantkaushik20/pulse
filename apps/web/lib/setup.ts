export type TenantRole = "OWNER" | "MEMBER";

export type TenantProfile = {
  name: string;
  role: TenantRole;
};

export type Mailbox = {
  id: string;
  externalAccountId: string;
  status: string;
  lastSyncedAt: string | null;
  lastErrorCode: string | null;
};

export type Workspace =
  | { kind: "needs-tenant" }
  | { kind: "needs-mailbox"; role: TenantRole; mailbox: Mailbox | null }
  | { kind: "ready"; role: TenantRole; mailbox: Mailbox };

export class SetupHttpError extends Error {
  readonly status: number;

  constructor(status: number) {
    super("setup request failed");
    this.name = "SetupHttpError";
    this.status = status;
  }
}

export async function loadWorkspace(
  baseUrl: string,
  token: string,
  fetchImpl: typeof fetch = fetch,
): Promise<Workspace> {
  const profile = await loadProfile(baseUrl, token, fetchImpl);
  if (profile === null) {
    return { kind: "needs-tenant" };
  }
  const mailboxes = await loadMailboxes(baseUrl, token, fetchImpl);
  const active = mailboxes.find((mailbox) => mailbox.status === "ACTIVE") ?? null;
  if (active === null) {
    return { kind: "needs-mailbox", role: profile.role, mailbox: mailboxes[0] ?? null };
  }
  return { kind: "ready", role: profile.role, mailbox: active };
}

export async function createTenant(
  baseUrl: string,
  token: string,
  name: string,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const response = await fetchImpl(`${baseUrl}/tenants`, {
    method: "POST",
    headers: { ...authorizationHeaders(token), "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    throw new SetupHttpError(response.status);
  }
}

export async function startGmailConnect(
  baseUrl: string,
  token: string,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  const response = await fetchImpl(`${baseUrl}/integrations/gmail/connect`, {
    method: "POST",
    headers: authorizationHeaders(token),
  });
  if (!response.ok) {
    throw new SetupHttpError(response.status);
  }
  const body: unknown = await response.json();
  if (!isRecord(body) || typeof body.authorization_url !== "string") {
    throw new SetupHttpError(502);
  }
  if (!isGoogleAuthorizationUrl(body.authorization_url)) {
    throw new SetupHttpError(502);
  }
  return body.authorization_url;
}

export function isGoogleAuthorizationUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === "accounts.google.com";
  } catch {
    return false;
  }
}

export async function syncMailbox(
  baseUrl: string,
  token: string,
  connectionId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const response = await fetchImpl(
    `${baseUrl}/integrations/gmail/connections/${encodeURIComponent(connectionId)}/sync`,
    { method: "POST", headers: authorizationHeaders(token) },
  );
  if (!response.ok) {
    throw new SetupHttpError(response.status);
  }
}

export async function disconnectMailbox(
  baseUrl: string,
  token: string,
  connectionId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const response = await fetchImpl(
    `${baseUrl}/integrations/gmail/connections/${encodeURIComponent(connectionId)}/disconnect`,
    { method: "POST", headers: authorizationHeaders(token) },
  );
  if (!response.ok) {
    throw new SetupHttpError(response.status);
  }
}

export function gmailRedirectNotice(search: string): string | null {
  const params = new URLSearchParams(search);
  if (params.get("gmail") === "connected") {
    return "Gmail is connected.";
  }
  if (params.get("gmail") === "error") {
    const reason = params.get("reason") ?? "failed";
    if (!/^[a-z_]{1,32}$/.test(reason)) {
      return "Gmail could not be connected.";
    }
    return `Gmail could not be connected (${reason}).`;
  }
  return null;
}

async function loadProfile(
  baseUrl: string,
  token: string,
  fetchImpl: typeof fetch,
): Promise<TenantProfile | null> {
  const response = await fetchImpl(`${baseUrl}/me`, { headers: authorizationHeaders(token) });
  if (!response.ok) {
    throw new SetupHttpError(response.status);
  }
  const body: unknown = await response.json();
  if (!isRecord(body)) {
    throw new SetupHttpError(502);
  }
  if (body.tenant === null || body.tenant === undefined) {
    return null;
  }
  if (!isRecord(body.tenant)) {
    throw new SetupHttpError(502);
  }
  const role = body.tenant.role;
  if (role !== "OWNER" && role !== "MEMBER") {
    throw new SetupHttpError(502);
  }
  return { name: requiredString(body.tenant.name), role };
}

async function loadMailboxes(
  baseUrl: string,
  token: string,
  fetchImpl: typeof fetch,
): Promise<Mailbox[]> {
  const response = await fetchImpl(`${baseUrl}/integrations/gmail/connections`, {
    headers: authorizationHeaders(token),
  });
  if (!response.ok) {
    throw new SetupHttpError(response.status);
  }
  const body: unknown = await response.json();
  if (!isRecord(body) || !Array.isArray(body.items)) {
    throw new SetupHttpError(502);
  }
  return body.items.map(parseMailbox);
}

function parseMailbox(value: unknown): Mailbox {
  if (!isRecord(value)) {
    throw new SetupHttpError(502);
  }
  return {
    id: requiredString(value.id),
    externalAccountId: requiredString(value.external_account_id),
    status: requiredString(value.status),
    lastSyncedAt: optionalString(value.last_synced_at),
    lastErrorCode: optionalString(value.last_error_code),
  };
}

function authorizationHeaders(token: string): { Accept: string; Authorization: string } {
  if (token.trim() === "" || /[\r\n]/.test(token)) {
    throw new SetupHttpError(401);
  }
  return {
    Accept: "application/json",
    Authorization: `Bearer ${token}`,
  };
}

function requiredString(value: unknown): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new SetupHttpError(502);
  }
  return value;
}

function optionalString(value: unknown): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value !== "string") {
    throw new SetupHttpError(502);
  }
  return value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
