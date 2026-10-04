import { describe, expect, it } from "vitest";

import { formatAge } from "./age";

const now = new Date(2026, 9, 3, 15, 0, 0);

describe("formatAge", () => {
  it("uses the viewer's local calendar without changing the stored instant", () => {
    expect(formatAge(new Date(2026, 9, 3, 14, 59, 30).toISOString(), now)).toBe("Just now");
    expect(formatAge(new Date(2026, 9, 3, 14, 45, 0).toISOString(), now)).toBe("15 min ago");
    expect(formatAge(new Date(2026, 9, 3, 13, 0, 0).toISOString(), now)).toBe("2 hours ago");
    expect(formatAge(new Date(2026, 9, 2, 10, 0, 0).toISOString(), now)).toBe("Yesterday");
    expect(formatAge(new Date(2026, 8, 30, 15, 0, 0).toISOString(), now)).toBe("3 days ago");
  });
});
