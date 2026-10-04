import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import HomePage from "./page";

describe("home page", () => {
  it("asks what needs attention and stays signed out when Clerk is not configured", () => {
    const html = renderToStaticMarkup(<HomePage />);

    expect(html).toContain("What needs your attention?");
    expect(html).toContain("Sign-in is not configured for this environment.");
    expect(html).not.toContain("You're all caught up");
    expect(html).not.toContain("Pulse could not load what needs your attention.");
  });
});
