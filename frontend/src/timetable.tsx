import React, { useEffect, useState } from "react";
import { api, Child } from "./api";
import "./timetable.css";

type Lesson = { weekday: number; start: string; end: string; subject: string; room: string; teacher: string };
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
    return <section key={day}><h4>{day}</h4>{items.length ? items.map((lesson, i) => <div className="timetable-lesson" key={i}>
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
      {item.currentLesson && <p>{item.currentLesson.start}–{item.currentLesson.end} Uhr{item.currentLesson.room && ` · Raum ${item.currentLesson.room}`}</p>}
      {item.nextLesson && <p>Danach: {item.nextLesson.subject} ab {item.nextLesson.start} Uhr</p>}
      {item.configured ? <details><summary>Wochenstundenplan anzeigen</summary><Week lessons={item.weeklySchedule}/><small>Planmäßiger Unterricht · {item.timezone}. Vertretungen und Ferien werden nicht automatisch übernommen.</small></details>
      : <p>Unter Personen kannst du den Stundenplan hochladen oder selbst anlegen.</p>}
    </article>)}
  </section>;
}

export function TimetableManagement({ children }: { children: Child[] }) {
  const [selected, setSelected] = useState<Child | null>(null);
  if (!children.length) return null;
  return <section className="timetable-management">
    <h2>Stundenpläne der Kinder</h2><p>Wochenplan ansehen, selbst bearbeiten oder aus einem Bild bzw. einer PDF übernehmen.</p>
    <div className="timetable-children">{children.map(child => <button className="secondary" key={child.id} onClick={() => setSelected(child)}>{child.display_name} · Stundenplan</button>)}</div>
    {selected && <TimetableEditor key={selected.id} child={selected} close={() => setSelected(null)}/>}
  </section>;
}

function TimetableEditor({ child, close }: { child: Child; close: () => void }) {
  const [plan, setPlan] = useState<Plan>(blankPlan);
  const [loaded, setLoaded] = useState(false);
  const [editable, setEditable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [preview, setPreview] = useState<{ url: string; pdf: boolean } | null>(null);
  const [proposal, setProposal] = useState<{ lessons: Lesson[]; extractedText: string; message: string } | null>(null);
  const [dayOff, setDayOff] = useState("");
  useEffect(() => {
    let active = true;
    api<Snapshot>(`/children/${child.id}/timetable`, {cache:"no-store"}).then(result => {
      if (active) { setPlan(result.plan); setEditable(result.canEdit); setLoaded(true); }
    }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [child.id]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview.url); }, [preview]);
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
  async function upload(file: File) {
    setError(""); setNotice(""); setProposal(null);
    if (file.size > 10 * 1024 * 1024) { setError("Die Datei darf höchstens 10 MB groß sein."); return; }
    setPreview({url: URL.createObjectURL(file), pdf: file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")});
    setBusy(true);
    const form = new FormData(); form.append("file", file);
    try {
      const result = await api<{lessons:Lesson[];extractedText:string;message:string}>(`/children/${child.id}/timetable/analyze`, {method:"POST",body:form});
      setProposal(result);
    } catch(e) { setError((e as Error).message); }
    finally { setBusy(false); }
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
      <p>Bild oder PDF hochladen oder die Stunden unten selbst eintragen. Es entstehen keine Kalendertermine.</p>
      <label>Stundenplan hochladen (PNG, JPEG, WebP oder PDF; höchstens 10 MB / 3 PDF-Seiten)
        <input type="file" accept="image/png,image/jpeg,image/webp,application/pdf" disabled={busy} onChange={event => { const file=event.target.files?.[0]; if (file) void upload(file); event.target.value=""; }}/>
      </label>
      {busy && <p role="status">Wird verarbeitet …</p>}
      {preview && <details open><summary>Hochgeladene Vorlage</summary>{preview.pdf ? <object className="timetable-preview" data={preview.url} type="application/pdf"><a href={preview.url} target="_blank" rel="noreferrer">PDF öffnen</a></object> : <img className="timetable-preview" src={preview.url} alt="Hochgeladener Stundenplan zum Abgleichen"/>}</details>}
      {proposal && <div className="timetable-proposal"><p>{proposal.message}</p>
        {!!proposal.lessons.length && <><Week lessons={proposal.lessons}/><button type="button" disabled={busy} onClick={() => {
          if (plan.lessons.length && !confirm("Die aktuellen Einträge im Bearbeitungsformular durch den Vorschlag ersetzen? Gespeichert wird erst mit „Stundenplan speichern“.")) return;
          change({...plan,lessons:proposal.lessons}); setProposal(null);
        }}>Vorschlag zur Bearbeitung übernehmen</button></>}
        <details><summary>Erkannten Text anzeigen</summary><pre>{proposal.extractedText || "Kein Text erkannt"}</pre></details>
      </div>}
      <form onSubmit={save}><fieldset disabled={busy}>
        <div className="timetable-settings">
          <label>Gültig ab<input type="date" value={plan.valid_from || ""} onChange={e => change({...plan,valid_from:e.target.value || null})}/></label>
          <label>Gültig bis<input type="date" value={plan.valid_until || ""} min={plan.valid_from || undefined} onChange={e => change({...plan,valid_until:e.target.value || null})}/></label>
          <label>Zeitzone<input required value={plan.timezone} onChange={e => change({...plan,timezone:e.target.value})}/></label>
        </div>
        <p>Zeiten gelten in der angegebenen Zeitzone. Lücken zwischen Stunden werden als Pause angezeigt.</p>
        <div className="timetable-rows">{plan.lessons.map((lesson,index) => <div className="timetable-row" key={index}>
          <label>Tag<select value={lesson.weekday} onChange={e => changeLesson(index,{weekday:Number(e.target.value)})}>{days.map((day,i) => <option value={i} key={day}>{day}</option>)}</select></label>
          <label>Von<input type="time" required value={lesson.start} onChange={e => changeLesson(index,{start:e.target.value})}/></label>
          <label>Bis<input type="time" required value={lesson.end} onChange={e => changeLesson(index,{end:e.target.value})}/></label>
          <label>Fach<input required maxLength={160} value={lesson.subject} onChange={e => changeLesson(index,{subject:e.target.value})}/></label>
          <label>Raum<input maxLength={100} value={lesson.room} onChange={e => changeLesson(index,{room:e.target.value})}/></label>
          <label>Lehrkraft<input maxLength={160} value={lesson.teacher} onChange={e => changeLesson(index,{teacher:e.target.value})}/></label>
          <button type="button" className="secondary" aria-label={`Stunde ${index+1} entfernen`} onClick={() => change({...plan,lessons:plan.lessons.filter((_,i) => i !== index)})}>Entfernen</button>
        </div>)}</div>
        <button type="button" className="secondary" disabled={plan.lessons.length >= 150} onClick={() => change({...plan,lessons:[...plan.lessons,{weekday:0,start:"08:00",end:"08:45",subject:"",room:"",teacher:""}]})}>+ Unterrichtsstunde</button>
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
