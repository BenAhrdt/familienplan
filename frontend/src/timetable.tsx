import React, { useEffect, useState } from "react";
import { api, Child } from "./api";
import "./timetable.css";
import { Copy, Trash2 } from "lucide-react";

import { copyDay, copyLesson, type Lesson } from "./timetable-copy";

type Plan = { timezone: string; valid_from: string | null; valid_until: string | null; days_off: string[]; lessons: Lesson[] };
type Snapshot = {
  childId: number; childName: string; status: string; statusText: string; timezone: string;
  currentLesson: Lesson | null; nextLesson: Lesson | null; dailySchedule: Lesson[];
  weeklySchedule: Lesson[]; configured: boolean; canEdit: boolean; plan: Plan;
};
const days = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"];
const blankPlan = (): Plan => ({ timezone: "Europe/Berlin", valid_from: null, valid_until: null, days_off: [], lessons: [] });

function Week({ lessons }: { lessons: Lesson[] }) {
  return <div className="timetable-week">{days.map((day, index) => {
    const items = lessons.filter(x => x.weekday === index).sort((a,b) => a.start.localeCompare(b.start));
    if (index > 4 && !items.length) return null;
    return <section key={day}><h4>{day}</h4>{items.length ? items.map((lesson, i) => <div className="timetable-lesson" style={{borderLeftColor: lesson.color || "#3979b8"}} key={i}>
      <small>{lesson.start}–{lesson.end}</small><strong>{lesson.subject}</strong>
      {(lesson.room || lesson.teacher) && <small>{[lesson.room && `Raum ${lesson.room}`, lesson.teacher].filter(Boolean).join(" · ")}</small>}
    </div>) : <p>Kein Unterricht</p>}</section>;
  })}</div>;
}

export function TimetableOverview({ children }: { children: Child[] }) {
  const [items, setItems] = useState<Snapshot[]>([]);
  const [error, setError] = useState("");
  const childKey = children.map(x => x.id).join(",");
  useEffect(() => {
    let active = true;
    let running = false;
    async function refresh() {
      if (running) return;
      running = true;
      try {
        const result = await Promise.all(children.map(child => api<Snapshot>(`/children/${child.id}/timetable`, { background: true, cache: "no-store" })));
        if (active) { setItems(result); setError(""); }
      } catch {
        if (active) { setItems([]); setError("Der aktuelle Stundenplan konnte nicht geladen werden."); }
      } finally { running = false; }
    }
    void refresh();
    const timer = window.setInterval(refresh, 15000);
    const visible = () => { if (!document.hidden) void refresh(); };
    document.addEventListener("visibilitychange", visible);
    return () => { active = false; window.clearInterval(timer); document.removeEventListener("visibilitychange", visible); };
  }, [childKey]);
  if (!children.length) return null;
  return <section className="timetable-overview" aria-label="Stundenpläne der Kinder">
    <div className="sectiontitle"><h2>Stundenplan</h2></div>
    {error && <p role="alert" className="error">{error}</p>}
    {!items.length && !error && <p>Stundenpläne werden geladen …</p>}
    {items.map(item => <article className="timetable-card" key={item.childId}>
      <strong>{item.childName}{item.status === "lesson" ? " hat aktuell: " : " · "}{item.statusText}</strong>
      {item.currentLesson && <p>{item.currentLesson.start}–{item.currentLesson.end} Uhr{item.currentLesson.teacher && ` · ${item.currentLesson.teacher}`}{item.currentLesson.room && ` · Raum ${item.currentLesson.room}`}</p>}
      {item.nextLesson && <p>Danach: {item.nextLesson.subject} ab {item.nextLesson.start} Uhr</p>}
      {item.configured ? <details><summary>Wochenstundenplan anzeigen</summary><Week lessons={item.weeklySchedule}/></details>
      : <p>Unter Kinder kannst du beim jeweiligen Kind den Stundenplan anlegen.</p>}
    </article>)}
  </section>;
}

export function TimetableManagement({ child }: { child: Child }) {
  const [open, setOpen] = useState(false);
  return <>
    <button type="button" className="secondary" onClick={() => setOpen(true)} aria-label={`Stundenplan für ${child.display_name}`}>Stundenplan</button>
    {open && <TimetableEditor key={child.id} child={child} close={() => setOpen(false)}/>}
  </>;
}

function TimetableEditor({ child, close }: { child: Child; close: () => void }) {
  const [plan, setPlan] = useState<Plan>(blankPlan);
  const [loaded, setLoaded] = useState(false);
  const [editable, setEditable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [copyFrom, setCopyFrom] = useState(0);
  const [copyTo, setCopyTo] = useState(1);
  const [dayOff, setDayOff] = useState("");
  useEffect(() => {
    let active = true;
    api<Snapshot>(`/children/${child.id}/timetable`, {cache:"no-store"}).then(result => {
      if (active) { setPlan(result.plan); setEditable(result.canEdit); setLoaded(true); }
    }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [child.id]);
  useEffect(() => {
    const prevent = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", prevent);
    return () => window.removeEventListener("beforeunload", prevent);
  }, [dirty]);
  function change(next: Plan) { setPlan(next); setDirty(true); setNotice(""); }
  function changeLesson(index: number, value: Partial<Lesson>) {
    change({...plan, lessons: plan.lessons.map((lesson,i) => i === index ? {...lesson,...value} : lesson)});
  }
  function dismiss() { if (!busy && (!dirty || confirm("Ungespeicherte Änderungen verwerfen?"))) close(); }
  function duplicateDay() {
    try { change({...plan, lessons: copyDay(plan.lessons, copyFrom, copyTo)}); setError(""); }
    catch (e) { setError((e as Error).message); }
  }
  function duplicateLesson(index: number) {
    try { change({...plan, lessons: copyLesson(plan.lessons, index)}); setError(""); }
    catch (e) { setError((e as Error).message); }
  }
  async function save(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const result = await api<Snapshot>(`/children/${child.id}/timetable`, {method:"PUT",body:JSON.stringify(plan)});
      setPlan(result.plan); setDirty(false); setNotice("Stundenplan gespeichert.");
    } catch(e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="modal"><div className="panel timetable-editor" role="dialog" aria-modal="true" aria-labelledby="timetable-title">
    <button type="button" className="close" aria-label="Schließen" onClick={dismiss} disabled={busy}>×</button>
    <h2 id="timetable-title">Stundenplan · {child.display_name}</h2>
    {error && <p role="alert" className="error">{error}</p>}{notice && <p role="status">{notice}</p>}
    {!loaded && !error && <p>Wird geladen …</p>}
    {loaded && !editable && <><p>Du kannst diesen Stundenplan ansehen.</p><Week lessons={plan.lessons}/></>}
    {loaded && editable && <>
      <p>Stunden eintragen oder bestehende Stunden und Tage duplizieren. Es entstehen keine Kalendertermine.</p>
      {busy && <p role="status">Wird gespeichert …</p>}
      <form onSubmit={save}><fieldset disabled={busy}>
        <div className="timetable-settings">
          <label>Gültig ab<input type="date" value={plan.valid_from || ""} onChange={e => change({...plan,valid_from:e.target.value || null})}/></label>
          <label>Gültig bis<input type="date" value={plan.valid_until || ""} min={plan.valid_from || undefined} onChange={e => change({...plan,valid_until:e.target.value || null})}/></label>
          <label>Zeitzone<input required value={plan.timezone} onChange={e => change({...plan,timezone:e.target.value})}/></label>
        </div>
        <p>Zeiten gelten in der angegebenen Zeitzone. Lücken zwischen Stunden werden als Pause angezeigt.</p>
        <div className="timetable-settings">
          <label>Tag kopieren<select value={copyFrom} onChange={e => setCopyFrom(Number(e.target.value))}>{days.map((day,i) => <option key={day} value={i}>{day}</option>)}</select></label>
          <label>Nach<select value={copyTo} onChange={e => setCopyTo(Number(e.target.value))}>{days.map((day,i) => <option key={day} value={i}>{day}</option>)}</select></label>
          <button type="button" className="secondary" onClick={duplicateDay} disabled={copyFrom === copyTo || !plan.lessons.some(x => x.weekday === copyFrom) || plan.lessons.length + plan.lessons.filter(x => x.weekday === copyFrom).length > 150}>Tag duplizieren</button>
        </div>
        <p>Stundenkopien folgen im nächsten freien Zeitraum desselben Tages. Tageskopien behalten Zeiten, Fächer, Lehrkräfte und Farben bei.</p>
        <div className="timetable-rows">{days.map((day, weekday) => {
          const entries = plan.lessons.map((lesson, index) => ({lesson, index})).filter(x => x.lesson.weekday === weekday);
          return <section className="timetable-day" key={day} aria-label={day}>
            <header className="timetable-day-heading"><h3>{day}</h3><span>{entries.length} {entries.length === 1 ? "Stunde" : "Stunden"}</span>
              <button type="button" className="secondary" disabled={plan.lessons.length >= 150} onClick={() => change({...plan,lessons:[...plan.lessons,{weekday,start:"08:00",end:"08:45",subject:"",room:"",teacher:"",color:"#3979b8"}]})}>+ Stunde</button>
            </header>
            {entries.length > 0 && <div className="timetable-column-headings" aria-hidden="true"><span>Von</span><span>Bis</span><span>Fach</span><span>Raum</span><span>Lehrkraft</span><span>Farbe</span><span>Aktionen</span></div>}
            {entries.map(({lesson,index}) => <div className="timetable-row" key={index}>
              <label><span>Von</span><input type="time" required value={lesson.start} onChange={e => changeLesson(index,{start:e.target.value})}/></label>
              <label><span>Bis</span><input type="time" required value={lesson.end} onChange={e => changeLesson(index,{end:e.target.value})}/></label>
              <label><span>Fach</span><input required maxLength={160} value={lesson.subject} onChange={e => changeLesson(index,{subject:e.target.value})}/></label>
              <label><span>Raum</span><input maxLength={100} value={lesson.room} onChange={e => changeLesson(index,{room:e.target.value})}/></label>
              <label><span>Lehrkraft</span><input maxLength={160} value={lesson.teacher} onChange={e => changeLesson(index,{teacher:e.target.value})}/></label>
              <label><span>Farbe</span><input type="color" value={lesson.color || "#3979b8"} onChange={e => changeLesson(index,{color:e.target.value})}/></label>
              <div className="timetable-row-actions">
                <button type="button" className="secondary" title="Stunde duplizieren" aria-label={`${day} ${lesson.start}: Stunde duplizieren`} disabled={plan.lessons.length >= 150} onClick={() => duplicateLesson(index)}><Copy size={16}/></button>
                <button type="button" className="secondary" title="Stunde entfernen" aria-label={`${day} ${lesson.start}: Stunde entfernen`} onClick={() => change({...plan,lessons:plan.lessons.filter((_,i) => i !== index)})}><Trash2 size={16}/></button>
                <details className="timetable-move"><summary>Verschieben</summary><label>Nach<select value={lesson.weekday} onChange={e => changeLesson(index,{weekday:Number(e.target.value)})}>{days.map((name,i) => <option value={i} key={name}>{name}</option>)}</select></label></details>
              </div>
            </div>)}
          </section>;
        })}</div>
        <details className="timetable-days-off"><summary>Unterrichtsfreie Tage ({plan.days_off.length})</summary>
          <p>Ferien, Feiertage und Ausfälle werden nicht automatisch erkannt. Hier eingetragene Tage erhalten den Status „Heute kein Unterricht“.</p>
          <label>Freier Tag<input type="date" value={dayOff} onChange={e => setDayOff(e.target.value)}/></label>
          <button type="button" className="secondary" disabled={!dayOff || plan.days_off.length >= 370} onClick={() => { change({...plan,days_off:[...new Set([...plan.days_off,dayOff])].sort()}); setDayOff(""); }}>Tag ergänzen</button>
          <ul>{plan.days_off.map(day => <li key={day}>{day} <button className="secondary" type="button" aria-label={`Freien Tag ${day} entfernen`} onClick={() => change({...plan,days_off:plan.days_off.filter(x => x !== day)})}>Entfernen</button></li>)}</ul>
        </details>
        <div className="modalactions"><button type="submit">Stundenplan speichern</button><button type="button" className="secondary" onClick={dismiss}>Schließen</button></div>
      </fieldset></form>
    </>}
  </div></div>;
}
