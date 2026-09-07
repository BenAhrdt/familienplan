import { describe, expect, it } from "vitest";
import { allDayRange } from "./event-dates";

describe("Ganztagstermine", () => {
  it.each([
    ["2026-09-03T15:30", "2026-09-03T00:00", "2026-09-04T00:00"],
    ["2026-09-09", "2026-09-09T00:00", "2026-09-10T00:00"],
    ["2026-12-31", "2026-12-31T00:00", "2027-01-01T00:00"],
    ["2028-02-29", "2028-02-29T00:00", "2028-03-01T00:00"],
    ["2026-03-29", "2026-03-29T00:00", "2026-03-30T00:00"],
    ["2026-10-25", "2026-10-25T00:00", "2026-10-26T00:00"],
  ])("hält lokale Mitternachtsgrenzen für %s ein", (input,start,end) => {
    expect(allDayRange(input)).toEqual({start,end});
  });
  it("erlaubt das Leeren des Beginns vor einer neuen Datumseingabe", () => {
    expect(allDayRange("")).toEqual({start:"",end:""});
  });
});
