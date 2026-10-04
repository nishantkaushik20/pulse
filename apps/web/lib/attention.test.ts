import { describe, expect, it, vi } from "vitest";

import { attentionContext, loadAttention, resolveAttention, withoutItem } from "./attention";

const item = {
  id: "item-1",
  type: "email_review",
  title: "New email needs review",
  description: "From: jane@acme.com\nSubject: Proposal for Q4",
  priority: "MEDIUM" as const,
  status: "OPEN" as const,
  created_at: "2026-10-03T13:00:00.000Z",
  source: "gmail",
  entity_type: "message",
  entity_id: "message-1",
  thread_id: null,
  customer_name: null,
  match_method: null,
  body_text: "SECRET-BODY-TEXT",
  tenant_id: "tenant-secret",
};

describe("attention client", () => {
  it("keeps sender and subject and drops the body", () => {
    expect(attentionContext(item.description)).toEqual({
      from: "From: jane@acme.com",
      subject: "Subject: Proposal for Q4",
      text: null,
    });
  });

  it("loads only the inbox fields", async () => {
    const fetchImpl = vi.fn(async () => Response.json({ items: [item] }));
    const items = await loadAttention("http://api.test", "session-token", fetchImpl);
    expect(items).toEqual([
      {
        id: "item-1",
        type: "email_review",
        title: "New email needs review",
        description: "From: jane@acme.com\nSubject: Proposal for Q4",
        priority: "MEDIUM",
        status: "OPEN",
        created_at: "2026-10-03T13:00:00.000Z",
        source: "gmail",
        entity_type: "message",
        entity_id: "message-1",
        thread_id: null,
        customer_name: null,
        match_method: null,
      },
    ]);
    expect(JSON.stringify(items)).not.toContain("SECRET-BODY-TEXT");
    expect(JSON.stringify(items)).not.toContain("tenant-secret");
    expect(fetchImpl).toHaveBeenCalledWith("http://api.test/attention", {
      headers: { Accept: "application/json", Authorization: "Bearer session-token" },
    });
  });

  it("treats a failed inbox response as an error and keeps the token out of the message", async () => {
    const fetchImpl = vi.fn(async () => new Response("nope", { status: 401 }));
    await expect(loadAttention("http://api.test", "session-token", fetchImpl)).rejects.toThrow(
      "attention request failed",
    );
    await expect(loadAttention("http://api.test", "session-token", fetchImpl)).rejects.toThrow(
      expect.not.objectContaining({ message: expect.stringContaining("session-token") }),
    );
  });

  it("resolves by id with the session token and removes the item after success", async () => {
    const fetchImpl = vi.fn(async () => new Response(null, { status: 200 }));
    await resolveAttention("http://api.test", item.id, "session-token", fetchImpl);
    expect(fetchImpl).toHaveBeenCalledWith("http://api.test/attention/item-1/resolve", {
      method: "POST",
      headers: { Accept: "application/json", Authorization: "Bearer session-token" },
    });
    expect(withoutItem([item], item.id)).toEqual([]);
  });
});
