export type Lesson = { weekday: number; start: string; end: string; subject: string; room: string; teacher: string; color: string };

export function copyDay(lessons: Lesson[], from: number, to: number): Lesson[] {
  const copies = lessons.filter(x => x.weekday === from).map(x => ({...x, weekday: to}));
  if (from === to || !copies.length) throw new Error("Bitte einen belegten Ausgangstag und einen anderen Zieltag wählen.");
  if (lessons.length + copies.length > 150) throw new Error("Es sind höchstens 150 Stunden möglich.");
  const target = lessons.filter(x => x.weekday === to);
  if (copies.some(x => target.some(y => x.start < y.end && y.start < x.end))) {
    throw new Error("Der Zieltag enthält überschneidende Stunden. Bitte einen anderen Tag wählen oder die betroffenen Stunden zuerst anpassen.");
  }
  return [...lessons, ...copies];
}

export function copyLesson(lessons: Lesson[], index: number): Lesson[] {
  if (lessons.length >= 150) throw new Error("Es sind höchstens 150 Stunden möglich.");
  const lesson = lessons[index];
  const minutes = (value: string) => Number(value.slice(0,2)) * 60 + Number(value.slice(3));
  const duration = minutes(lesson.end) - minutes(lesson.start);
  let start = minutes(lesson.end);
  for (const other of lessons.filter(x => x.weekday === lesson.weekday).sort((a,b) => a.start.localeCompare(b.start))) {
    if (start < minutes(other.end) && start + duration > minutes(other.start)) start = minutes(other.end);
  }
  if (!Number.isFinite(duration) || !Number.isFinite(start) || duration <= 0 || start + duration >= 1440) {
    throw new Error("Für diese Kopie ist am selben Tag kein passender Zeitraum frei. Bitte die Zeiten prüfen oder den Tag duplizieren.");
  }
  const time = (value: number) => `${String(Math.floor(value / 60)).padStart(2,"0")}:${String(value % 60).padStart(2,"0")}`;
  return [...lessons, {...lesson, start: time(start), end: time(start + duration)}];
}
