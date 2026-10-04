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
    const items = await loadAttention("http://api.test", fetchImpl);
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
      },
    ]);
    expect(JSON.stringify(items)).not.toContain("SECRET-BODY-TEXT");
    expect(JSON.stringify(items)).not.toContain("tenant-secret");
  });

  it("treats a failed inbox response as an error", async () => {
    const fetchImpl = vi.fn(async () => new Response("nope", { status: 401 }));
    await expect(loadAttention("http://api.test", fetchImpl)).rejects.toThrow(
      "attention request failed",
    );
  });

  it("resolves by id and removes the item after success", async () => {
    const fetchImpl = vi.fn(async () => new Response(null, { status: 200 }));
    await resolveAttention("http://api.test", item.id, fetchImpl);
    expect(fetchImpl).toHaveBeenCalledWith("http://api.test/attention/item-1/resolve", {
      method: "POST",
      headers: { Accept: "application/json" },
    });
    expect(withoutItem([item], item.id)).toEqual([]);
  });
});
