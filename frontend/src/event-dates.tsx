import React, { useRef, useState } from "react";
import { CalendarDays } from "lucide-react";

export function allDayRange(value: string): { start: string; end: string } {
  const day = value.split("T")[0];
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return { start: "", end: "" };
  // Calendar arithmetic, independent of 23/25-hour daylight-saving days.
  const next = new Date(`${day}T12:00:00Z`);
  next.setUTCDate(next.getUTCDate() + 1);
  return { start: `${day}T00:00`, end: `${next.toISOString().slice(0, 10)}T00:00` };
}

function DateInput({ label, type, value, onChange, min }: {
  label: string; type: "date" | "datetime-local"; value: string;
  onChange: (value: string) => void; min?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  return <label>{label}<span className="event-date-input">
    <input ref={input} type={type} value={value} required min={min} onChange={event => onChange(event.target.value)}/>
    <button type="button" className="secondary" aria-label={`${label}: Datum auswählen`} title="Datum auswählen" onClick={() => {
      try { if (input.current?.showPicker) input.current.showPicker(); else input.current?.focus(); }
      catch { input.current?.focus(); }
    }}><CalendarDays size={18}/></button>
  </span></label>;
}

export function EventDateFields({ allDay, onAllDayChange, initialStart, initialEnd }: {
  allDay: boolean; onAllDayChange: (checked: boolean) => void; initialStart: string; initialEnd: string;
}) {
  const [range, setRange] = useState(() => allDay ? allDayRange(initialStart) : {start: initialStart, end: initialEnd});
  return <>
    <label className="check event-all-day"><input type="checkbox" checked={allDay} onChange={event => {
      if (event.target.checked) setRange(allDayRange(range.start));
      onAllDayChange(event.target.checked);
    }}/>Ganztägig</label>
    <input type="hidden" name="starts_at" value={range.start}/>
    <input type="hidden" name="ends_at" value={range.end}/>
    <div className="grid2">
      <DateInput label="Beginn" type={allDay ? "date" : "datetime-local"} value={allDay ? range.start.split("T")[0] : range.start}
        onChange={value => setRange(allDay ? allDayRange(value) : {...range,start:value})}/>
      {allDay ? <label>Ende (automatisch)<output className="event-date-end">{range.end ? `${range.end.slice(8,10)}.${range.end.slice(5,7)}.${range.end.slice(0,4)} 00:00 Uhr` : "Bitte Beginn wählen"}</output></label>
        : <DateInput label="Ende" type="datetime-local" value={range.end} min={range.start} onChange={value => setRange({...range,end:value})}/>}
    </div>
    {allDay && <p className="hint">Ganztägig: vom gewählten Tag um 00:00 Uhr bis zum Folgetag um 00:00 Uhr.</p>}
  </>;
}
