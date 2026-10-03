import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import HomePage from "./page";

describe("home page", () => {
  it("renders the product name and health link", () => {
    const html = renderToStaticMarkup(<HomePage />);

    expect(html).toContain("Pulse");
    expect(html).toContain("/health");
  });
});
