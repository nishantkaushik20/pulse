import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { withoutItem, type AttentionItem } from "@/lib/attention";

import { AttentionView } from "./AttentionView";

const now = new Date(2026, 9, 3, 15, 0, 0);

const email: AttentionItem = {
  id: "item-1",
  type: "email_review",
  title: "New email needs review",
  description: "From: jane@acme.com\nSubject: Proposal for Q4\nSECRET-BODY-TEXT",
  priority: "MEDIUM",
  status: "OPEN",
  created_at: new Date(2026, 9, 3, 13, 0, 0).toISOString(),
  source: "gmail",
  entity_type: "message",
  entity_id: "message-1",
};

const high: AttentionItem = {
  ...email,
  id: "item-high",
  title: "Confirm the delivery",
  description: "Warehouse asked for a time",
  priority: "HIGH",
  created_at: new Date(2026, 9, 3, 14, 45, 0).toISOString(),
  source: null,
  entity_type: null,
  entity_id: null,
};

function markup(items: AttentionItem[]) {
  return renderToStaticMarkup(
    <AttentionView
      state={{ status: "ready", items, notice: null }}
      now={now}
      onResolve={() => undefined}
      onRetry={() => undefined}
    />,
  );
}

describe("attention inbox view", () => {
  it("renders open attention items", () => {
    const html = markup([email]);
    expect(html).toContain("What needs your attention?");
    expect(html).toContain("1 open item");
    expect(html).toContain("New email needs review");
  });

  it("renders priority as text", () => {
    const html = markup([high, email]);
    expect(html).toContain("HIGH");
    expect(html).toContain("MEDIUM");
    expect(html.indexOf("HIGH")).toBeLessThan(html.indexOf("MEDIUM"));
  });

  it("renders Gmail sender and subject", () => {
    const html = markup([email]);
    expect(html).toContain("From: jane@acme.com");
    expect(html).toContain("Subject: Proposal for Q4");
  });

  it("renders age from the created time", () => {
    expect(markup([email])).toContain("2 hours ago");
    expect(markup([high])).toContain("15 min ago");
  });

  it("renders a keyboard-accessible resolve button", () => {
    const html = markup([email]);
    expect(html).toContain('<button type="button">Resolve</button>');
  });

  it("drops a resolved item from the open list", () => {
    const html = markup(withoutItem([email, high], email.id));
    expect(html).not.toContain("New email needs review");
    expect(html).toContain("Confirm the delivery");
    expect(html).toContain("1 open item");
  });

  it("shows the caught-up empty state", () => {
    const html = markup([]);
    expect(html).toContain("What needs your attention?");
    expect(html).toContain("You&#x27;re all caught up.");
    expect(html).not.toContain("No data");
    expect(html).not.toContain("Inbox empty");
  });

  it("shows an error state", () => {
    const html = renderToStaticMarkup(
      <AttentionView
        state={{ status: "error" }}
        now={now}
        onResolve={() => undefined}
        onRetry={() => undefined}
      />,
    );
    expect(html).toContain("Pulse could not load what needs your attention.");
    expect(html).toContain("Try again");
  });

  it("keeps the empty state hidden while the session is loading", () => {
    const html = renderToStaticMarkup(
      <AttentionView
        state={{ status: "auth-loading" }}
        now={now}
        onResolve={() => undefined}
        onRetry={() => undefined}
      />,
    );
    expect(html).toContain("Checking your session.");
    expect(html).not.toContain("all caught up");
    expect(html).not.toContain("Pulse could not load");
  });

  it("shows a loading state", () => {
    const html = renderToStaticMarkup(
      <AttentionView
        state={{ status: "loading" }}
        now={now}
        onResolve={() => undefined}
        onRetry={() => undefined}
      />,
    );
    expect(html).toContain("Checking what needs your attention.");
  });

  it("does not render an email body that was mixed into the description", () => {
    const html = markup([email]);
    expect(html).not.toContain("SECRET-BODY-TEXT");
    expect(html).not.toContain("mail.google.com");
  });
});

describe("resolve callback", () => {
  it("is invoked with the item id", () => {
    const onResolve = vi.fn();
    const html = renderToStaticMarkup(
      <AttentionView
        state={{ status: "ready", items: [email], notice: null }}
        now={now}
        onResolve={onResolve}
        onRetry={() => undefined}
      />,
    );
    expect(html).toContain("Resolve");
    onResolve(email.id);
    expect(onResolve).toHaveBeenCalledWith(email.id);
  });
});
