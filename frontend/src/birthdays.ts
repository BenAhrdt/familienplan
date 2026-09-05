/** The same annual occurrence rule as the integration calendar. */
export function birthdayOccursOnDay(birthDate: string, day: Date): boolean {
  const [year, month, date] = birthDate.split("-").map(Number);
  if (!year || !month || !date || day.getFullYear() < year) return false;
  const lastDay = new Date(day.getFullYear(), month, 0).getDate();
  return day.getMonth() === month - 1 && day.getDate() === Math.min(date, lastDay);
}
