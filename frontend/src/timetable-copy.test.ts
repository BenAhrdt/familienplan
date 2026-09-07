import { describe, expect, it } from "vitest";
import { copyDay, copyLesson, type Lesson } from "./timetable-copy";
const lesson: Lesson = {weekday: 0, start: "08:00", end: "08:45", subject: "Mathe", teacher: "Frau Müller", room: "12", color: "#abcdef"};
describe("Stunden kopieren", () => {
  it("übernimmt Details und überspringt belegte Zeiträume auch bei unsortierten Einträgen", () => {
    const original = [lesson, {...lesson, start: "09:30", end: "10:15"}, {...lesson, start: "08:45", end: "09:30"}];
    expect(copyLesson(original, 0).at(-1)).toEqual({...lesson, start: "10:15", end: "11:00"});
    expect(original).toHaveLength(3);
  });
  it("nutzt eine ausreichend große Lücke und ignoriert andere Tage", () => {
    expect(copyLesson([lesson, {...lesson, start: "09:30", end: "10:15"}, {...lesson, weekday: 1, start: "08:45", end: "09:30"}], 0).at(-1)).toEqual({...lesson, start: "08:45", end: "09:30"});
  });
  it("verhindert Tagesüberlauf und ungültige Dauer", () => {
    expect(() => copyLesson([{...lesson, start: "23:00", end: "23:45"}],0)).toThrow();
    expect(() => copyLesson([{...lesson, end: "07:00"}],0)).toThrow();
  });
});
describe("Tage kopieren", () => {
  it("behält vorhandene Stunden bei und kopiert Details unabhängig", () => {
    const target = {...lesson, weekday: 1, start: "08:45", end: "09:30"};
    const result = copyDay([lesson, target],0,1);
    expect(result).toEqual([lesson, target, {...lesson, weekday: 1}]);
    expect(result[2]).not.toBe(lesson);
  });
  it("verhindert Überschneidungen, gleiche Tage und leere Ausgangstage", () => {
    expect(() => copyDay([lesson, {...lesson, weekday: 1}],0,1)).toThrow(/überschneidende/);
    expect(() => copyDay([lesson],0,0)).toThrow();
    expect(() => copyDay([lesson],2,1)).toThrow();
  });
  it("beachtet die maximale Anzahl", () => {
    const full = Array.from({length:150}, () => ({...lesson}));
    expect(() => copyDay(full,0,1)).toThrow(/150/);
    expect(() => copyLesson(full,0)).toThrow(/150/);
  });
});
