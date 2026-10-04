/**
 * @vitest-environment jsdom
 */
import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ClerkReady } from "@/components/auth/ClerkReady";

import { AttentionInbox } from "./AttentionInbox";

const session = vi.hoisted(() => ({
  isLoaded: false,
  isSignedIn: false as boolean | undefined,
  getToken: vi.fn(async () => null as string | null),
}));

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => session,
  SignInButton: ({ children }: { children?: ReactNode }) => <>{children}</>,
}));

const item = {
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
};

let root: Root | null = null;
let host: HTMLDivElement | null = null;

beforeEach(() => {
  session.isLoaded = false;
  session.isSignedIn = false;
  session.getToken.mockReset();
  session.getToken.mockResolvedValue(null);
  vi.stubGlobal("fetch", vi.fn());
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => {
    root?.unmount();
  });
  host?.remove();
  vi.unstubAllGlobals();
});

function renderInbox() {
  act(() => {
    root?.render(
      <ClerkReady ready>
        <AttentionInbox />
      </ClerkReady>,
    );
  });
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("attention inbox session", () => {
  it("does not call the attention API while Clerk is still loading", async () => {
    renderInbox();
    await flush();

    expect(host?.textContent).toContain("Checking your session.");
    expect(host?.textContent).not.toContain("You're all caught up");
    expect(host?.textContent).not.toContain("Pulse could not load");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("shows Clerk sign-in and does not call the API when signed out", async () => {
    session.isLoaded = true;
    session.isSignedIn = false;
    renderInbox();
    await flush();

    expect(host?.textContent).toContain("Sign in to see what needs your attention.");
    expect(host?.querySelector("button")?.textContent).toBe("Sign in");
    expect(host?.textContent).not.toContain("Pulse could not load");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("sends the Clerk session token and renders open items", async () => {
    session.isLoaded = true;
    session.isSignedIn = true;
    session.getToken.mockResolvedValue("session-token");
    vi.mocked(fetch).mockResolvedValue(Response.json({ items: [item] }));

    renderInbox();
    await flush();

    expect(fetch).toHaveBeenCalledWith("http://localhost:8000/attention", {
      headers: { Accept: "application/json", Authorization: "Bearer session-token" },
    });
    expect(host?.textContent).toContain("New email needs review");
    expect(host?.textContent).toContain("From: jane@acme.com");
    expect(host?.innerHTML).not.toContain("session-token");
  });

  it("resolves with the same session token and removes the item", async () => {
    session.isLoaded = true;
    session.isSignedIn = true;
    session.getToken.mockResolvedValue("session-token");
    vi.mocked(fetch)
      .mockResolvedValueOnce(Response.json({ items: [item] }))
      .mockResolvedValueOnce(new Response(null, { status: 200 }));

    renderInbox();
    await flush();
    const button = host?.querySelector("article button");
    expect(button?.textContent).toBe("Resolve");
    await act(async () => {
      button?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(fetch).toHaveBeenLastCalledWith("http://localhost:8000/attention/item-1/resolve", {
      method: "POST",
      headers: { Accept: "application/json", Authorization: "Bearer session-token" },
    });
    expect(host?.textContent).not.toContain("New email needs review");
    expect(host?.textContent).toContain("You're all caught up");
    expect(host?.innerHTML).not.toContain("session-token");
  });

  it("returns to sign-in after one 401 and does not keep requesting", async () => {
    session.isLoaded = true;
    session.isSignedIn = true;
    session.getToken.mockResolvedValue("session-token");
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 401 }));

    renderInbox();
    await flush();
    await flush();

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(host?.textContent).toContain("Sign in");
    expect(host?.textContent).not.toContain("Pulse could not load");
    expect(host?.innerHTML).not.toContain("session-token");
  });
});
