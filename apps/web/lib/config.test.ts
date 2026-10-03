import { afterEach, describe, expect, it } from "vitest";

import { apiBaseUrl } from "./config";

describe("apiBaseUrl", () => {
  afterEach(() => {
    delete process.env.NEXT_PUBLIC_API_URL;
  });

  it("defaults to the local API", () => {
    delete process.env.NEXT_PUBLIC_API_URL;
    expect(apiBaseUrl()).toBe("http://localhost:8000");
  });

  it("reads the public API URL from the environment", () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.test";
    expect(apiBaseUrl()).toBe("https://api.example.test");
  });
});
