import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import HomePage from "./page";

describe("home page", () => {
  it("asks what needs attention while the inbox loads", () => {
    const html = renderToStaticMarkup(<HomePage />);

    expect(html).toContain("What needs your attention?");
    expect(html).toContain("Checking what needs your attention.");
  });
});
