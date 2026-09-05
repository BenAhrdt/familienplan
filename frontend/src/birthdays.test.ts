import { describe, expect, it } from "vitest";
import { birthdayOccursOnDay } from "./birthdays";

describe("annual birthdays", () => {
  it("uses February 28 only in non-leap years", () => {
    expect(birthdayOccursOnDay("2000-02-29", new Date(2026, 1, 28))).toBe(true);
    expect(birthdayOccursOnDay("2000-02-29", new Date(2028, 1, 28))).toBe(false);
    expect(birthdayOccursOnDay("2000-02-29", new Date(2028, 1, 29))).toBe(true);
  });
  it("recurs annually but never before birth", () => {
    expect(birthdayOccursOnDay("2011-09-11", new Date(2010, 8, 11))).toBe(false);
    expect(birthdayOccursOnDay("2011-09-11", new Date(2027, 8, 11))).toBe(true);
    expect(birthdayOccursOnDay("2011-09-11", new Date(2027, 8, 12))).toBe(false);
  });
});
