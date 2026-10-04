import { describe, expect, it, vi } from "vitest";

import {
  createTenant,
  gmailRedirectNotice,
  isGoogleAuthorizationUrl,
  loadWorkspace,
  startGmailConnect,
  syncMailbox,
} from "./setup";

const me = {
  user: { id: "user-1", clerk_user_id: "clerk", email: "ada@example.com", name: "Ada" },
  tenant: { id: "tenant-1", name: "Acme", role: "OWNER" },
};

const mailbox = {
  id: "conn-1",
  external_account_id: "ada@gmail.com",
  status: "ACTIVE",
  last_synced_at: null,
  last_error_code: null,
  encrypted_refresh_token: "secret",
};

function route(url: string): Response {
  if (url.endsWith("/me")) {
    return Response.json(me);
  }
  if (url.endsWith("/integrations/gmail/connections")) {
    return Response.json({ items: [mailbox] });
  }
  return new Response(null, { status: 404 });
}

describe("setup client", () => {
  it("loads an active mailbox without token fields", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => route(String(input)));
    const workspace = await loadWorkspace("http://api.test", "session-token", fetchImpl);
    expect(workspace).toEqual({
      kind: "ready",
      role: "OWNER",
      mailbox: {
        id: "conn-1",
        externalAccountId: "ada@gmail.com",
        status: "ACTIVE",
        lastSyncedAt: null,
        lastErrorCode: null,
      },
    });
    expect(JSON.stringify(workspace)).not.toContain("secret");
  });

  it("asks for a business when the profile has no tenant", async () => {
    const fetchImpl = vi.fn(async () => Response.json({ ...me, tenant: null }));
    await expect(loadWorkspace("http://api.test", "token", fetchImpl)).resolves.toEqual({
      kind: "needs-tenant",
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("creates a tenant without a tenant id", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      Response.json({ id: "t", name: "Acme", role: "OWNER" }),
    );
    await createTenant("http://api.test", "token", "Acme", fetchImpl);
    const init = fetchImpl.mock.calls[0]?.[1];
    if (init === undefined) {
      throw new Error("missing request");
    }
    expect(init.body).toBe(JSON.stringify({ name: "Acme" }));
    expect(String(init.body)).not.toContain("tenant_id");
  });

  it("starts Gmail connect only for a Google authorization URL", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      Response.json({
        authorization_url: "https://accounts.google.com/o/oauth2/v2/auth?state=opaque",
      }),
    );
    const url = await startGmailConnect("http://api.test", "token", fetchImpl);
    expect(isGoogleAuthorizationUrl(url)).toBe(true);
    const init = fetchImpl.mock.calls[0]?.[1];
    if (init === undefined) {
      throw new Error("missing request");
    }
    expect(init.method).toBe("POST");
    expect(init.body).toBeUndefined();
  });

  it("rejects a connect URL that is not Google", async () => {
    const fetchImpl = vi.fn(async () =>
      Response.json({ authorization_url: "https://evil.example/steal" }),
    );
    await expect(startGmailConnect("http://api.test", "token", fetchImpl)).rejects.toMatchObject({
      status: 502,
    });
  });

  it("syncs a connection the server already scoped", async () => {
    const fetchImpl = vi.fn(async () => Response.json({ examined: 1, ingested: 1, skipped: 0 }));
    await syncMailbox("http://api.test", "token", "conn-1", fetchImpl);
    expect(fetchImpl).toHaveBeenCalledWith(
      "http://api.test/integrations/gmail/connections/conn-1/sync",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("keeps redirect reasons to a short code", () => {
    expect(gmailRedirectNotice("?gmail=connected")).toBe("Gmail is connected.");
    expect(gmailRedirectNotice("?gmail=error&reason=conflict")).toBe(
      "Gmail could not be connected (conflict).",
    );
    expect(gmailRedirectNotice("?gmail=error&reason=<script>")).toBe(
      "Gmail could not be connected.",
    );
  });
});
