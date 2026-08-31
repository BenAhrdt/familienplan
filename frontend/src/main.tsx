import React, { FormEvent, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Bell,
  Cake,
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Copy,
  Home,
  LogOut,
  Menu,
  Palette,
  Palmtree,
  Plus,
  Search,
  Trash2,
  UserPlus,
  Users,
} from "lucide-react";
import {
  api,
  AppNotification,
  Birthday,
  CalendarEvent,
  ChangeRequest,
  Child,
  EventType,
  getSessionUser,
  Holiday,
  Institution,
  PersonAccess,
  SearchResult,
  setCsrf,
  Stay,
  User,
} from "./api";
import "./styles.css";
import "./people.css";
import "./clipboard";
import "./theme.css";
import "./calendar.css";
import "./dashboard.css";

type Screen =
  | "home"
  | "calendar"
  | "children"
  | "people"
  | "birthdays"
  | "waste"
  | "holidays"
  | "planning"
  | "settings";
type HolidayPlanningDraft = Holiday & { child_id: number | null };
type PlanningItem = HolidayPlanningDraft & {
  id: string;
  kind: "FERIEN" | "FEIERTAG" | "BRUECKENTAG" | "FREI";
  responsible_user_id: number | null;
  starts_time?: string;
  ends_time?: string;
};
type SectionAccess = { birthdays: number[]; waste_collection: number[] };
type WasteCalendarSetting = {
  enabled: boolean; provider: "AWIDO" | "ICAL"; customer: string; city: string;
  street: string; calendar_url: string; color: string; visible_to_user_ids: number[];
  type_colors: Record<string, string>;
  last_sync_at: string | null; last_result: { events?: number; removed?: number; years?: number[] } | null; last_error: string | null;
};
type CalendarSourceStatus = { id: number; name: string; kind: string; active: boolean; last_sync_at: string | null; last_result: Record<string, unknown> | null; last_error: string | null };
type CalendarColorPreferences = { holiday_color: string; birthday_color: string; school_color: string; waste_color: string };
type ApplicationMeta = {
  version: string;
  latest_version: string | null;
  update_available: boolean;
  release_url: string | null;
  repository: string | null;
  changelog: string;
  update_check_error: string | null;
};
const labels = {
  home: "Übersicht",
  calendar: "Kalender",
  children: "Kinder",
  people: "Personen",
  birthdays: "Geburtstage",
  waste: "Abfallkalender",
  holidays: "Ferien & Feiertage",
  planning: "Planung zusammenstellen",
  settings: "Einstellungen",
};
const federalStates = [
  ["BW", "Baden-Württemberg"],
  ["BY", "Bayern"],
  ["BE", "Berlin"],
  ["BB", "Brandenburg"],
  ["HB", "Bremen"],
  ["HH", "Hamburg"],
  ["HE", "Hessen"],
  ["MV", "Mecklenburg-Vorpommern"],
  ["NI", "Niedersachsen"],
  ["NW", "Nordrhein-Westfalen"],
  ["RP", "Rheinland-Pfalz"],
  ["SL", "Saarland"],
  ["SN", "Sachsen"],
  ["ST", "Sachsen-Anhalt"],
  ["SH", "Schleswig-Holstein"],
  ["TH", "Thüringen"],
];
const eventTypeLabels: Record<EventType, string> = {
  STAY: "Betreuung",
  BIRTHDAY: "Geburtstag",
  GENERAL: "Allgemein",
  SCHOOL: "Schule",
  CLEANING: "Putzfrau",
  WASTE: "Abfallkalender",
  PRIVATE: "Privat",
  OTHER: "Sonstiges",
};
const childlessEventTypes = new Set<EventType>(["BIRTHDAY", "CLEANING", "WASTE"]);
const wasteTypeLabels: Record<string, string> = {
  bio: "Bioabfall", yellow: "Gelbe Tonne", residual: "Restabfall",
  paper: "Altpapier", hazardous: "Schadstoff / Sondermüll", other: "Sonstige Abfälle",
};
const sortedEventTypes = (types: EventType[]) =>
  [...types].sort((left, right) => {
    if (left === "OTHER") return 1;
    if (right === "OTHER") return -1;
    return eventTypeLabels[left].localeCompare(eventTypeLabels[right], "de");
  });
const eventDisplayColor = (event: CalendarEvent) =>
  event.event_type === "SCHOOL"
    ? "var(--school)"
    : event.event_type === "BIRTHDAY"
      ? "var(--birthday)"
      : event.event_type === "WASTE"
        ? event.color || "var(--waste, #5C8B58)"
      : event.color || "#8B6CC1";
const eventTypeDisplayColor = (type: EventType) => type === "SCHOOL" ? "var(--school)" : type === "BIRTHDAY" ? "var(--birthday)" : type === "WASTE" ? "var(--waste, #5C8B58)" : type === "STAY" ? "var(--green)" : type === "CLEANING" ? "#35A853" : type === "PRIVATE" ? "#9A477E" : type === "GENERAL" ? "#8B6CC1" : "#6F63B6";

const localDateKey = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

function calendarEventOccursOnDay(event: CalendarEvent, day: Date, dayEnd: Date) {
  if (event.all_day) {
    const start = event.raw_data?.all_day_start;
    const end = event.raw_data?.all_day_end_exclusive;
    if (typeof start === "string" && typeof end === "string") {
      const dayKey = localDateKey(day);
      return start <= dayKey && dayKey < end;
    }
  }
  return new Date(event.starts_at) < dayEnd && new Date(event.ends_at) > day;
}

function calendarEventTiming(event: CalendarEvent) {
  if (event.all_day) {
    const startKey = event.raw_data?.all_day_start;
    const endKey = event.raw_data?.all_day_end_exclusive;
    if (typeof startKey === "string" && typeof endKey === "string") {
      const start = new Date(`${startKey}T12:00:00`);
      const endExclusive = new Date(`${endKey}T12:00:00`);
      const lastDay = new Date(endExclusive);
      lastDay.setDate(lastDay.getDate() - 1);
      const format = (date: Date) => date.toLocaleDateString("de-DE");
      return `${format(start)}${localDateKey(start) === localDateKey(lastDay) ? "" : ` – ${format(lastDay)}`} · ganztägig`;
    }
    return `${new Date(event.starts_at).toLocaleDateString("de-DE")} · ganztägig`;
  }
  return `${new Date(event.starts_at).toLocaleString("de-DE")} – ${new Date(event.ends_at).toLocaleString("de-DE")}`;
}

function calendarEventTimeOnDay(event: CalendarEvent, day: Date, dayEnd: Date) {
  if (event.all_day) return "";
  const startsAt = new Date(event.starts_at);
  const endsAt = new Date(event.ends_at);
  const time = (date: Date) => date.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  const startsBeforeOrAtDay = startsAt.getTime() <= day.getTime();
  const endsAfterOrAtDay = endsAt.getTime() >= dayEnd.getTime();
  if (startsBeforeOrAtDay && endsAfterOrAtDay) return "ganztägig";
  if (!startsBeforeOrAtDay && endsAfterOrAtDay) return `ab ${time(startsAt)}`;
  if (startsBeforeOrAtDay && !endsAfterOrAtDay) return `bis ${time(endsAt)}`;
  return `${time(startsAt)}–${time(endsAt)}`;
}

function clientId() {
  return globalThis.crypto?.randomUUID?.() ||
    `local-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function Field({
  label,
  name,
  type = "text",
  required = true,
  defaultValue,
}: {
  label: string;
  name: string;
  type?: string;
  required?: boolean;
  defaultValue?: string;
}) {
  return (
    <label>
      {label}
      <input
        name={name}
        type={type}
        required={required}
        defaultValue={defaultValue}
      />
    </label>
  );
}

function AudiencePicker({
  people,
  initialValues,
  privateDefault = false,
}: {
  people: User[];
  initialValues: number[] | null | undefined;
  privateDefault?: boolean;
}) {
  const currentUserId = getSessionUser()?.id;
  const selectablePeople = people.filter((person) => person.id !== currentUserId);
  const initial = (initialValues ?? (privateDefault ? [] : selectablePeople.map((person) => person.id)))
    .filter((id) => id !== currentUserId);
  const [selected, setSelected] = useState<number[]>(initial),
    [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);
  const names = selectablePeople
    .filter((person) => selected.includes(person.id))
    .map((person) => person.display_name);
  const summary =
    selected.length === selectablePeople.length && selectablePeople.length > 0
      ? "Alle Personen"
      : names.length
        ? names.join(", ")
        : "Nur ich";
  return (
    <div className="audience-field">
      <span className="audience-label">Sichtbar für</span>
      {selected.map((id) => (
        <input key={id} type="hidden" name="visible_to_user_ids" value={id} />
      ))}
      <button
        type="button"
        className="audience-trigger"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
      >
        <span>{summary}</span>
        <b>{selected.length || 1}</b>
      </button>
      {open && (
        <>
          <button
            type="button"
            className="audience-backdrop"
            aria-label="Auswahl schließen"
            onClick={() => setOpen(false)}
          />
          <section className="audience-popover" role="dialog" aria-label="Sichtbare Personen auswählen">
            <header>
              <strong>Sichtbar für</strong>
              <button type="button" onClick={() => setOpen(false)}>×</button>
            </header>
            <div className="audience-list">
              {selectablePeople.map((person) => (
                <label key={person.id} className="audience-person-tag" style={{"--person-color":person.color} as React.CSSProperties}>
                  <input
                    type="checkbox"
                    checked={selected.includes(person.id)}
                    onChange={(event) =>
                      setSelected((current) =>
                        event.target.checked
                          ? [...current, person.id]
                          : current.filter((id) => id !== person.id),
                      )
                    }
                  />
                  <span><i>{person.display_name.slice(0,1).toUpperCase()}</i>{person.display_name}</span>
                </label>
              ))}
            </div>
            <p>Du selbst hast immer Zugriff.</p>
            <button type="button" className="audience-done" onClick={() => setOpen(false)}>Fertig</button>
          </section>
        </>
      )}
    </div>
  );
}

function ChildStar({ child }: { child: Child }) {
  return <svg className="care-child-star" viewBox="0 0 100 100" role="img" aria-label={child.display_name}>
    <title>{child.display_name}</title>
    <path fill={child.color} d="M50 2 61.5 35.2 96.7 35.9 68.6 57.2 78.8 91 50 71.4 21.2 91 31.4 57.2 3.3 35.9 38.5 35.2Z" />
    <text x="50" y="60" textAnchor="middle">{child.display_name.slice(0, 1).toUpperCase()}</text>
  </svg>;
}

function CareMarkers({ child, responsible }: { child: Child; responsible: User }) {
  return <span className="care-markers" aria-label={`${responsible.display_name} betreut ${child.display_name}`}>
    <i className="care-person-marker" style={{ backgroundColor: responsible.color }} title={responsible.display_name}>
      {responsible.display_name.slice(0, 1).toUpperCase()}
    </i>
    <ChildStar child={child} />
  </span>;
}

function Setup({ done }: { done: (u: User) => void }) {
  const [error, setError] = useState("");
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    const d = Object.fromEntries(new FormData(e.currentTarget));
    try {
      const r = await api<{ user: User; csrf_token: string }>("/setup/admin", {
        method: "POST",
        body: JSON.stringify(d),
      });
      setCsrf(r.csrf_token);
      done(r.user);
    } catch (x) {
      setError((x as Error).message);
    }
  }
  return (
    <main className="auth">
      <section className="auth-copy">
        <span className="eyebrow">Willkommen bei FamilienPlan</span>
        <h1>
          Gemeinsam planen.
          <br />
          Ruhiger durch den Alltag.
        </h1>
        <p>
          Kalender, Betreuungszeiten und Ferien an einem sicheren Ort – für alle, die
          Familie organisieren.
        </p>
      </section>
      <form className="panel" onSubmit={submit}>
        <div className="mark">FP</div>
        <h2>Ersteinrichtung</h2>
        <p className="muted">Lege das erste Administratorkonto an.</p>
        {error && <p className="error">{error}</p>}
        <div className="grid2">
          <Field label="Benutzername" name="username" />
          <Field label="Anzeigename" name="display_name" />
        </div>
        <Field label="E-Mail-Adresse" name="email" type="email" />
        <div className="grid2">
          <Field
            label="Vorname (optional)"
            name="first_name"
            required={false}
          />
          <Field
            label="Nachname (optional)"
            name="last_name"
            required={false}
          />
        </div>
        <Field
          label="Passwort (mindestens 12 Zeichen)"
          name="password"
          type="password"
        />
        <Field
          label="Passwort bestätigen"
          name="password_confirm"
          type="password"
        />
        <button>
          FamilienPlan einrichten <ChevronRight size={18} />
        </button>
      </form>
    </main>
  );
}

function Login({ done }: { done: (u: User) => void }) {
  const [error, setError] = useState(""), [forgotOpen,setForgotOpen]=useState(false), [forgotMessage,setForgotMessage]=useState("");
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      const r = await api<{ user: User; csrf_token: string }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          username: f.get("username"),
          password: f.get("password"),
          remember: !!f.get("remember"),
        }),
      });
      setCsrf(r.csrf_token);
      done(r.user);
    } catch (x) {
      setError((x as Error).message);
    }
  }
  return (
    <main className="auth">
      <section className="auth-copy">
        <span className="eyebrow">FamilienPlan</span>
        <h1>
          Alles Wichtige.
          <br />
          Für alle im Blick.
        </h1>
        <p>Ein ruhiger Ort für den lebhaften Familienalltag.</p>
      </section>
      <form className="panel login" onSubmit={submit}>
        <div className="mark">FP</div>
        <h2>Schön, dass du da bist</h2>
        <p className="muted">Melde dich an, um weiterzuplanen.</p>
        {error && <p className="error">{error}</p>}
        <Field label="Benutzername" name="username" />
        <Field label="Passwort" name="password" type="password" />
        <label className="check">
          <input type="checkbox" name="remember" /> Angemeldet bleiben
        </label>
        <button>
          Anmelden <ChevronRight size={18} />
        </button>
        <button type="button" className="link-button" onClick={()=>{setForgotOpen(true);setForgotMessage("")}}>Passwort vergessen?</button>
      </form>
      {forgotOpen && <div className="modal"><form className="panel" onSubmit={async(e)=>{e.preventDefault();setError("");try{const f=new FormData(e.currentTarget);const result=await api<{message:string}>("/auth/password/forgot",{method:"POST",body:JSON.stringify({email:f.get("email")})});setForgotMessage(result.message)}catch(x){setError((x as Error).message)}}}><button type="button" className="close" onClick={()=>setForgotOpen(false)}>×</button><h2>Passwort zurücksetzen</h2><p className="muted">Du erhältst einen eine Stunde gültigen Einmal-Link. Dein bisheriges Passwort wird nicht per E-Mail versendet.</p>{error&&<p className="error">{error}</p>}{forgotMessage?<><p className="success">{forgotMessage}</p><button type="button" onClick={()=>setForgotOpen(false)}>Schließen</button></>:<><Field label="E-Mail-Adresse" name="email" type="email"/><button>Reset-Link anfordern</button></>}</form></div>}
    </main>
  );
}

function ResetPassword() {
  const token=location.pathname.split("/reset-password/")[1]||"", [message,setMessage]=useState(""), [error,setError]=useState("");
  async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();setError("");const f=new FormData(e.currentTarget);try{const result=await api<{message:string}>("/auth/password/reset",{method:"POST",body:JSON.stringify({token,password:f.get("password"),password_confirm:f.get("password_confirm")})});setMessage(result.message)}catch(x){setError((x as Error).message)}}
  return <main className="auth"><section className="auth-copy"><span className="eyebrow">FamilienPlan</span><h1>Neues Passwort festlegen.</h1></section>{message?<section className="panel"><h2>Passwort geändert</h2><p className="success">{message}</p><button onClick={()=>{history.replaceState({},"","/");location.reload()}}>Zur Anmeldung</button></section>:<form className="panel" onSubmit={submit}><h2>Passwort zurücksetzen</h2><p className="muted">Der Link kann nur einmal verwendet werden.</p>{error&&<p className="error">{error}</p>}<Field label="Neues Passwort (mindestens 12 Zeichen)" name="password" type="password"/><Field label="Passwort bestätigen" name="password_confirm" type="password"/><button>Passwort speichern</button></form>}</main>
}

type DashboardItem = {
  id: string;
  title: string;
  detail: string;
  startsAt: Date;
  color: string;
  kind: "Termin" | "Betreuung" | "Geburtstag";
};
type CalendarTarget = {
  kind: "event" | "stay" | "birthday";
  id: number;
  startsAt: string;
  relatedIds?: number[];
};
type DashboardConflict = {
  key: string;
  childName: string;
  firstPerson: string;
  secondPerson: string;
  startsAt: Date;
  endsAt: Date;
  stayIds: number[];
};

function Dashboard({
  children,
  people,
  openCalendar,
}: {
  children: Child[];
  people: User[];
  openCalendar: (target?: CalendarTarget) => void;
}) {
  const now = new Date();
  const [items, setItems] = useState<DashboardItem[]>([]),
    [conflicts, setConflicts] = useState<DashboardConflict[]>([]),
    [requests, setRequests] = useState<ChangeRequest[]>([]),
    [visibleItems, setVisibleItems] = useState(8),
    [loading, setLoading] = useState(true),
    [loadError, setLoadError] = useState("");
  const date = new Intl.DateTimeFormat("de-DE", {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(now);
  const childKey = children.map((child) => child.id).join(","),
    peopleColorKey = people.map((person) => `${person.id}:${person.color}`).join(",");
  useEffect(() => {
    let active = true;
    const from = new Date(),
      to = new Date(from.getTime() + 365 * 24 * 60 * 60 * 1000);
    setLoading(true);
    setLoadError("");
    Promise.all([
      api<CalendarEvent[]>(
        `/calendar?from_at=${from.toISOString()}&to_at=${to.toISOString()}`,
        { background: true },
      ),
      Promise.all(
        children.map((child) =>
          api<Stay[]>(
            `/children/${child.id}/stays?from_at=${from.toISOString()}&to_at=${to.toISOString()}`,
            { background: true },
          ),
        ),
      ),
      api<ChangeRequest[]>("/change-requests", { background: true }),
      api<Birthday[]>("/birthdays", { background: true }),
    ])
      .then(([events, staysByChild, openRequests, birthdays]) => {
        if (!active) return;
        const childNames = new Map(
          children.map((child) => [child.id, child.display_name]),
        );
        const upcoming: DashboardItem[] = [
          ...events.map((event) => ({
            id: `event-${event.id}`,
            title: event.title,
            detail: [
              event.child_id ? childNames.get(event.child_id) : "Ganze Familie",
              event.all_day ? "Ganztägig" : null,
            ]
              .filter(Boolean)
              .join(" · "),
            startsAt: new Date(event.starts_at),
            color: eventDisplayColor(event),
            kind: "Termin" as const,
          })),
          ...staysByChild.flat().map((stay) => ({
            id: `stay-${stay.id}`,
            title: `${childNames.get(stay.child_id) || "Kind"} bei ${stay.responsible_display_name || "–"}`,
            detail: stay.note || "Betreuungszeit",
            startsAt: new Date(stay.starts_at),
            color: people.find((person) => person.id === stay.responsible_user_id)?.color || "var(--green)",
            kind: "Betreuung" as const,
          })),
          ...birthdays.map((birthday) => {
            const birthDate = new Date(`${birthday.birth_date}T12:00:00`),
              next = new Date(from.getFullYear(), birthDate.getMonth(), birthDate.getDate(), 12);
            if (next < from) next.setFullYear(next.getFullYear() + 1);
            return {
              id: `birthday-${birthday.id}`,
              title: `🎂 ${birthday.display_name}`,
              detail: birthday.is_private ? "Privater Geburtstag" : "Geburtstag",
              startsAt: next,
              color: "var(--birthday)",
              kind: "Geburtstag" as const,
            };
          }),
        ]
          .filter((item) => !Number.isNaN(item.startsAt.getTime()))
          .sort((a, b) => a.startsAt.getTime() - b.startsAt.getTime());
        const allStays = staysByChild.flat(),
          detectedConflicts: DashboardConflict[] = [];
        for (let firstIndex = 0; firstIndex < allStays.length; firstIndex += 1) {
          const first = allStays[firstIndex];
          for (let secondIndex = firstIndex + 1; secondIndex < allStays.length; secondIndex += 1) {
            const second = allStays[secondIndex];
            if (
              first.child_id !== second.child_id ||
              first.responsible_user_id === second.responsible_user_id
            ) continue;
            const startsAt = new Date(
                Math.max(new Date(first.starts_at).getTime(), new Date(second.starts_at).getTime()),
              ),
              endsAt = new Date(
                Math.min(new Date(first.ends_at).getTime(), new Date(second.ends_at).getTime()),
              );
            if (startsAt >= endsAt) continue;
            detectedConflicts.push({
              key: [first.id, second.id].sort((a, b) => a - b).join("-"),
              childName: childNames.get(first.child_id) || "Kind",
              firstPerson: first.responsible_display_name || "Unbekannt",
              secondPerson: second.responsible_display_name || "Unbekannt",
              startsAt,
              endsAt,
              stayIds: [first.id, second.id],
            });
          }
        }
        setItems(upcoming);
        setConflicts(
          detectedConflicts.sort(
            (a, b) => a.startsAt.getTime() - b.startsAt.getTime(),
          ),
        );
        setRequests(openRequests);
      })
      .catch((error) => {
        if (active)
          setLoadError(
            error instanceof Error
              ? error.message
              : "Die nächsten Einträge konnten nicht geladen werden.",
          );
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [childKey, peopleColorKey]);
  const sessionUser = getSessionUser(),
    requestsToDecide = requests.filter(
      (request) => request.affected_user_id === sessionUser?.id,
    ).length;
  function itemDate(value: Date) {
    return new Intl.DateTimeFormat("de-DE", {
      weekday: "short",
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(value);
  }
  return (
    <>
      <header className="pagehead">
        <div>
          <span className="eyebrow">{date}</span>
          <h1>Familienüberblick</h1>
          <p>Alle vorhandenen Planungen auf einen Blick.</p>
        </div>
      </header>
      <div className="dashboard dashboardwide">
        {!!conflicts.length && (
          <section className="dashboardconflicts">
            <div className="sectiontitle">
              <h2>Planungskonflikte</h2>
              <span>{conflicts.length}</span>
            </div>
            <div className="conflictlist">
              {conflicts.slice(0, 8).map((conflict) => (
                <button
                  key={conflict.key}
                  onClick={() =>
                    openCalendar({
                      kind: "stay",
                      id: conflict.stayIds[0],
                      relatedIds: conflict.stayIds,
                      startsAt: conflict.startsAt.toISOString(),
                    })
                  }
                >
                  <strong>{conflict.childName} gleichzeitig bei {conflict.firstPerson} und {conflict.secondPerson}</strong>
                  <small>{itemDate(conflict.startsAt)} – {conflict.endsAt.toLocaleString("de-DE")}</small>
                  <ChevronRight size={18} />
                </button>
              ))}
              {conflicts.length > 8 && (
                <p>{conflicts.length - 8} weitere Konflikte werden im Kalender gekennzeichnet.</p>
              )}
            </div>
          </section>
        )}
        <section className="dashboardupcoming">
          <div className="sectiontitle">
            <h2>Als Nächstes</h2>
            {!!items.length && <button onClick={() => openCalendar()}>Zum Kalender</button>}
          </div>
          {loading ? (
            <div className="empty large"><p>Planungen werden geladen …</p></div>
          ) : loadError ? (
            <div className="empty large"><p>{loadError}</p></div>
          ) : items.length ? (
            <div className="timeline dashboardtimeline">
              {items.slice(0, visibleItems).map((item) => (
                <button
                  className="dashboarditem"
                  key={item.id}
                  onClick={() =>
                    openCalendar({
                      kind: item.id.startsWith("event-")
                        ? "event"
                        : item.id.startsWith("birthday-")
                          ? "birthday"
                          : "stay",
                      id: Number(item.id.split("-")[1]),
                      startsAt: item.startsAt.toISOString(),
                    })
                  }
                >
                  <i style={{ background: item.color }} />
                  <span>
                    <strong>{item.title}</strong>
                    <small>{itemDate(item.startsAt)} · {item.kind}</small>
                    {item.detail && <small>{item.detail}</small>}
                  </span>
                  <ChevronRight size={18} />
                </button>
              ))}
              {visibleItems < items.length && (
                <button
                  className="dashboardmore"
                  onClick={() => setVisibleItems((current) => current + 8)}
                >
                  Weitere anzeigen ({items.length - visibleItems})
                </button>
              )}
            </div>
          ) : (
            <div className="empty large">
              <CalendarDays />
              <h3>Noch keine Termine</h3>
              <p>In den nächsten zwölf Monaten ist nichts eingetragen.</p>
            </div>
          )}
        </section>
        <aside className={`action ${requests.length ? "hasrequests" : ""}`}>
          <span>
            <CheckCircle2 />
          </span>
          <div>
            <h3>{requests.length ? `${requests.length} offene ${requests.length === 1 ? "Abstimmung" : "Abstimmungen"}` : "Keine offenen Abstimmungen"}</h3>
            <p>{requests.length ? (requestsToDecide ? `${requestsToDecide} ${requestsToDecide === 1 ? "Anfrage wartet" : "Anfragen warten"} auf deine Entscheidung.` : "Deine Anfrage wartet noch auf eine Rückmeldung.") : "Neue Anfragen werden hier angezeigt."}</p>
          </div>
          {!!requests.length && <button onClick={() => openCalendar()}>Ansehen</button>}
        </aside>
      </div>
    </>
  );
}

function InstitutionPicker({
  kind,
  initial,
}: {
  kind: "school" | "care";
  initial?: Child;
}) {
  const prefix = kind;
  const title = kind === "school" ? "Schule" : "Betreuung";
  const [results, setResults] = useState<Institution[]>([]),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  function apply(item: Institution, form: HTMLFormElement) {
    (form.elements.namedItem(prefix) as HTMLInputElement).value = item.name;
    (form.elements.namedItem(prefix + "_city") as HTMLInputElement).value =
      item.city || "";
    (form.elements.namedItem(prefix + "_url") as HTMLInputElement).value =
      item.website || "";
    (
      form.elements.namedItem(prefix + "_calendar_url") as HTMLInputElement
    ).value = item.calendar_url || "";
    if (kind === "school") {
      (form.elements.namedItem("school_address") as HTMLInputElement).value =
        item.address || "";
      (
        form.elements.namedItem("school_state_code") as HTMLSelectElement
      ).value = item.state_code || "";
    }
    setMessage(
      item.calendar_url
        ? "Kalenderquelle erkannt und übernommen."
        : item.website
          ? "Homepage übernommen; dort wurde noch kein öffentlicher Kalender erkannt."
          : "Einrichtung übernommen.",
    );
  }
  async function search(e: React.MouseEvent<HTMLButtonElement>) {
    const form = e.currentTarget.form!;
    const name = (form.elements.namedItem(prefix) as HTMLInputElement).value;
    const city = (form.elements.namedItem(prefix + "_city") as HTMLInputElement)
      .value;
    if (name.trim().length < 2 || city.trim().length < 2) {
      setMessage("Bitte Name und Ort eingeben.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const q = new URLSearchParams({ kind, name, city });
      if (kind === "care") {
        const careUrl = (
          form.elements.namedItem("care_url") as HTMLInputElement
        ).value;
        const schoolUrl = (
          form.elements.namedItem("school_url") as HTMLInputElement
        ).value;
        if (careUrl || schoolUrl)
          q.set("context_url", careUrl || schoolUrl);
      }
      const found = await api<Institution[]>("/institutions/search?" + q);
      setResults(found);
      if (found.length === 1) apply(found[0], form);
      else if (!found.length)
        setMessage(
          "Kein Eintrag im öffentlichen Einrichtungsverzeichnis oder auf der gewählten Schulhomepage gefunden. Prüfe die Schreibweise oder speichere Name und Ort manuell.",
        );
    } catch (x) {
      setMessage((x as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function choose(item: Institution, e: React.MouseEvent<HTMLButtonElement>) {
    apply(item, e.currentTarget.form!);
    setResults([]);
  }
  return (
    <fieldset className="institution">
      <legend>{title}</legend>
      <div className="grid2">
        <Field
          label={`${title} (Name)`}
          name={prefix}
          required={false}
          defaultValue={(initial?.[prefix] as string) || ""}
        />
        <Field
          label="Ort"
          name={prefix + "_city"}
          required={false}
          defaultValue={
            (initial?.[`${prefix}_city` as keyof Child] as string) || ""
          }
        />
      </div>
      <Field
        label={`${title}-Homepage (optional)`}
        name={prefix + "_url"}
        type="url"
        required={false}
        defaultValue={
          (initial?.[`${prefix}_url` as keyof Child] as string) || ""
        }
      />
      {kind === "school" && (
        <>
          <Field
            label="Schuladresse"
            name="school_address"
            required={false}
            defaultValue={initial?.school_address || ""}
          />
          <label>
            Bundesland
            <select
              name="school_state_code"
              defaultValue={initial?.school_state_code || ""}
            >
              <option value="">Bitte auswählen</option>
              {federalStates.map(([code, name]) => (
                <option value={code} key={code}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </>
      )}
      <Field
        label="Öffentliche Kalenderadresse (optional)"
        name={prefix + "_calendar_url"}
        type="url"
        required={false}
        defaultValue={
          (initial?.[`${prefix}_calendar_url` as keyof Child] as string) || ""
        }
      />
      <button
        type="button"
        className="secondary"
        onClick={search}
        disabled={busy}
      >
        {busy ? "Suche läuft …" : `${title} suchen`}
      </button>
      {message && <p className="hint">{message}</p>}
      {results.length > 0 && (
        <div className="suggestions">
          {results.map((r, i) => (
            <button
              type="button"
              key={r.address || i}
              onClick={(e) => choose(r, e)}
            >
              <strong>{r.name}</strong>
              <small>{r.address}</small>
              {r.calendar_url && <span>Kalender gefunden</span>}
            </button>
          ))}
        </div>
      )}
    </fieldset>
  );
}

function Children({
  items,
  reload,
  people,
}: {
  items: Child[];
  reload: () => void;
  people: User[];
}) {
  const isAdmin = getSessionUser()?.role === "ADMIN";
  const [editing, setEditing] = useState<Child | null | undefined>(undefined),
    [error, setError] = useState("");
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const d: Record<string, unknown> = Object.fromEntries(
      new FormData(e.currentTarget),
    );
    if (d.birth_date === "") d.birth_date = null;
    if (d.default_responsible_user_id === "")
      d.default_responsible_user_id = null;
    else if (d.default_responsible_user_id)
      d.default_responsible_user_id = Number(d.default_responsible_user_id);
    if (d.school_state_code === "") d.school_state_code = null;
    try {
      await api(editing ? `/children/${editing.id}` : "/children", {
        method: editing ? "PUT" : "POST",
        body: JSON.stringify(d),
      });
      setEditing(undefined);
      reload();
    } catch (x) {
      setError((x as Error).message);
    }
  }
  return (
    <>
      <header className="pagehead">
        <div>
          <span className="eyebrow">Familie</span>
          <h1>Kinder</h1>
          <p>
            {isAdmin
              ? "Profile und Einrichtungen verwalten."
              : "Für dich freigegebene Kinder."}
          </p>
        </div>
        {isAdmin && (
          <button
            onClick={() => {
              setError("");
              setEditing(null);
            }}
          >
            <Plus size={18} /> Kind anlegen
          </button>
        )}
      </header>
      <div className="cards">
        {items.map((c) => (
          <button
            className="childcard"
            key={c.id}
            disabled={!isAdmin}
            onClick={() => {
              if (!isAdmin) return;
              setError("");
              setEditing(c);
            }}
          >
            <div className="avatar" style={{backgroundColor:c.color,color:"white"}}>{c.display_name[0]}</div>
            <h2>{c.display_name}</h2>
            <p>
              {c.school || "Keine Schule hinterlegt"}
              {c.school_class && ` · ${c.school_class}`}
            </p>
            <span className="tag">
              {isAdmin ? "Bearbeiten" : "Nur Ansicht"}
            </span>
          </button>
        ))}
      </div>
      {isAdmin && editing !== undefined && (
        <div className="modal">
          <form className="panel childform" onSubmit={submit}>
            <button
              type="button"
              className="close"
              onClick={() => setEditing(undefined)}
            >
              ×
            </button>
            <h2>{editing ? "Kind bearbeiten" : "Kind anlegen"}</h2>
            {error && <p className="error">{error}</p>}
            <div className="grid2">
              <label>
                Vorname
                <input
                  name="first_name"
                  required
                  defaultValue={editing?.first_name}
                />
              </label>
              <label>
                Nachname
                <input
                  name="last_name"
                  required
                  defaultValue={editing?.last_name}
                />
              </label>
            </div>
            <label>
              Anzeigename
              <input
                name="display_name"
                required
                defaultValue={editing?.display_name}
              />
            </label>
            <label>
              Geburtsdatum
              <input
                name="birth_date"
                type="date"
                defaultValue={editing?.birth_date || ""}
              />
            </label>
            <label>
              Kinderfarbe
              <div className="themepicker">
                <input name="color" type="color" defaultValue={editing?.color || "#426B5E"} />
                <span>Farbe für Stern und Kinderprofil</span>
              </div>
            </label>
            <label>
              Wohnt bei
              <select
                name="default_responsible_user_id"
                defaultValue={editing?.default_responsible_user_id || ""}
              >
                <option value="">Nicht festgelegt</option>
                {people.map((person) => (
                  <option value={person.id} key={person.id}>
                    {person.display_name}
                  </option>
                ))}
              </select>
            </label>
            <InstitutionPicker
              key={"school" + (editing?.id || "new")}
              kind="school"
              initial={editing || undefined}
            />
            <label>
              Klasse
              <input
                name="school_class"
                defaultValue={editing?.school_class || ""}
              />
            </label>
            {editing && (
              <>
                <input type="hidden" name="care" value={editing.care || ""} />
                <input type="hidden" name="care_city" value={editing.care_city || ""} />
                <input type="hidden" name="care_url" value={editing.care_url || ""} />
                <input type="hidden" name="care_calendar_url" value={editing.care_calendar_url || ""} />
              </>
            )}
            <label>
              Notizen
              <textarea name="notes" defaultValue={editing?.notes || ""} />
            </label>
            <button>Speichern</button>
          </form>
        </div>
      )}
    </>
  );
}

const localDateTime = (date: Date) => {
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return shifted.toISOString().slice(0, 16);
};

function CalendarScreen({
  children,
  people,
  holidayDraft,
  holidayDraftConsumed,
  target,
}: {
  children: Child[];
  people: User[];
  holidayDraft?: HolidayPlanningDraft | null;
  holidayDraftConsumed?: () => void;
  target?: CalendarTarget | null;
}) {
  const [events, setEvents] = useState<CalendarEvent[]>([]),
    [eventSeries, setEventSeries] = useState<CalendarEvent[]>([]),
    [stays, setStays] = useState<Stay[]>([]),
    [series, setSeries] = useState<Stay[]>([]),
    [requests, setRequests] = useState<ChangeRequest[]>([]),
    [holidays, setHolidays] = useState<Array<Holiday & { state: string }>>([]),
    [customBirthdays, setCustomBirthdays] = useState<Birthday[]>([]),
    [open, setOpen] = useState<"event" | "stay" | null>(null),
    [editingEvent, setEditingEvent] = useState<CalendarEvent | null>(null),
    [eventEditScope, setEventEditScope] = useState<
      "occurrence" | "future" | "series"
    >("occurrence"),
    [eventDeleteChoice, setEventDeleteChoice] =
      useState<CalendarEvent | null>(null),
    [editingStay, setEditingStay] = useState<Stay | null>(null),
    [stayToConvert, setStayToConvert] = useState<Stay | null>(null),
    [editingStaySource, setEditingStaySource] = useState<Stay | null>(null),
    [stayRangeMode, setStayRangeMode] = useState<"full" | "day">("full"),
    [counterRequest, setCounterRequest] = useState<ChangeRequest | null>(null),
    [rejectingRequest, setRejectingRequest] =
      useState<ChangeRequest | null>(null),
    [groupReview, setGroupReview] = useState<ChangeRequest | null>(null),
    [groupReviewItems, setGroupReviewItems] = useState<
      NonNullable<ChangeRequest["proposed_data"]["items"]>
    >([]),
    [groupReviewBusy, setGroupReviewBusy] = useState(false),
    [editScope, setEditScope] = useState<"occurrence" | "future" | "series">(
      "occurrence",
    ),
    [adminChoice, setAdminChoice] = useState<{
      stayId: number;
      update: Record<string, unknown>;
    } | null>(null),
    [adminCreateChoice, setAdminCreateChoice] = useState<Record<
      string,
      unknown
    > | null>(null),
    [createDraft, setCreateDraft] = useState<Record<string, unknown> | null>(
      null,
    ),
    [createConflicts, setCreateConflicts] = useState<Stay[]>([]),
    [repeatKind, setRepeatKind] = useState("once"),
    [eventRepeatKind, setEventRepeatKind] = useState("once"),
    [eventType, setEventType] = useState<EventType>("GENERAL"),
    [adminDeleteChoice, setAdminDeleteChoice] = useState<{
      stayId: number;
      scope: "occurrence" | "future" | "series";
    } | null>(null),
    [deleteProposalChoice, setDeleteProposalChoice] = useState<{
      stayId: number;
      scope: "occurrence" | "future" | "series";
      label: string;
    } | null>(null),
    [dayCreateChoice, setDayCreateChoice] = useState<{
      day: Date;
      holidays: Array<Holiday & { state: string }>;
    } | null>(null),
    [selectedDay, setSelectedDay] = useState<Date | null>(null),
    [readOnlyInfo, setReadOnlyInfo] = useState<{ title: string; message: string } | null>(null),
    [error, setError] = useState(""),
    [hiddenEventTypes, setHiddenEventTypes] = useState<EventType[]>(() => {
      try { return JSON.parse(localStorage.getItem("familienplan-calendar-hidden-types") || "[]"); }
      catch { return []; }
    }),
    [month, setMonth] = useState(() => {
      const initial = target ? new Date(target.startsAt) : new Date();
      return new Date(initial.getFullYear(), initial.getMonth(), 1);
    });
  const now = new Date(),
    canWriteCalendar = getSessionUser()?.role !== "VIEWER",
    availableEventTypes = getSessionUser()?.role === "ADMIN"
      ? sortedEventTypes(Object.keys(eventTypeLabels) as EventType[])
      : sortedEventTypes(Array.from(new Set([...(getSessionUser()?.allowed_event_types || []), "PRIVATE" as EventType]))),
    monthStart = new Date(month.getFullYear(), month.getMonth(), 1),
    firstWeekday = (monthStart.getDay() + 6) % 7,
    from = new Date(month.getFullYear(), month.getMonth(), 1 - firstWeekday),
    to = new Date(from.getFullYear(), from.getMonth(), from.getDate() + 42),
    days = Array.from(
      { length: 42 },
      (_, index) =>
        new Date(from.getFullYear(), from.getMonth(), from.getDate() + index),
    );
  function load() {
    api<CalendarEvent[]>(
      `/calendar?from_at=${from.toISOString()}&to_at=${to.toISOString()}`,
    ).then(setEvents);
    api<ChangeRequest[]>("/change-requests").then(setRequests);
    api<Stay[]>("/stay-series").then(setSeries);
    api<CalendarEvent[]>("/calendar-series").then(setEventSeries);
    api<Birthday[]>("/birthdays").then(setCustomBirthdays);
    Promise.all(
      children.map((c) =>
        api<Stay[]>(
          `/children/${c.id}/stays?from_at=${from.toISOString()}&to_at=${to.toISOString()}`,
        ),
      ),
    ).then((v) => setStays(v.flat()));
    const states = [
      ...new Set(
        children
          .map((child) => child.school_state_code)
          .filter((state): state is string => !!state),
      ),
    ];
    Promise.all(
      states.map((state) =>
        api<Holiday[]>(
          `/holidays?year=${month.getFullYear()}&state=${state}`,
        ).then((items) => items.map((item) => ({ ...item, state }))),
      ),
    ).then((values) => setHolidays(values.flat()));
  }
  useEffect(() => {
    const requestId = new URLSearchParams(location.search).get("request");
    if (!requestId || !requests.some((item) => String(item.id) === requestId)) return;
    const element = document.getElementById(`planning-request-${requestId}`);
    if (element) {
      element.scrollIntoView({ behavior: "smooth", block: "center" });
      element.classList.add("request-highlight");
      window.setTimeout(() => element.classList.remove("request-highlight"), 5000);
    }
  }, [requests]);
  useEffect(load, [children.length, month.getFullYear(), month.getMonth()]);
  useEffect(() => {
    const refresh = () => load();
    window.addEventListener("familienplan:data-changed", refresh);
    return () => window.removeEventListener("familienplan:data-changed", refresh);
  }, [children.length, month.getFullYear(), month.getMonth()]);
  useEffect(() => {
    if (!target) return;
    const targetDate = new Date(target.startsAt);
    if (
      targetDate.getFullYear() !== month.getFullYear() ||
      targetDate.getMonth() !== month.getMonth()
    ) {
      setMonth(new Date(targetDate.getFullYear(), targetDate.getMonth(), 1));
    }
  }, [target]);
  useEffect(() => {
    if (!target) return;
    const element = document.querySelector<HTMLElement>(
      `[data-calendar-target="${target.kind}-${target.id}"]`,
    );
    if (element) {
      window.setTimeout(
        () => element.scrollIntoView({ behavior: "smooth", block: "center" }),
        80,
      );
    }
  }, [target, events, stays]);
  useEffect(() => {
    if (!holidayDraft) return;
    const child = children.find((item) => item.id === holidayDraft.child_id);
    const startsAt = new Date(`${holidayDraft.starts_on}T00:00:00`);
    const endsAt = new Date(`${holidayDraft.ends_on}T00:00:00`);
    endsAt.setDate(endsAt.getDate() + 1);
    setMonth(new Date(startsAt.getFullYear(), startsAt.getMonth(), 1));
    setCreateDraft({
      child_id: child?.id,
      responsible_user_id:
        child?.default_responsible_user_id || getSessionUser()?.id,
      starts_at: startsAt.toISOString(),
      ends_at: endsAt.toISOString(),
      note: `Ferien: ${holidayDraft.name}`,
    });
    setSelectedDay(startsAt);
    setEditingStay(null);
    setRepeatKind("once");
    setOpen("stay");
    holidayDraftConsumed?.();
  }, [holidayDraft]);
  async function eventSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const eventInterval =
      eventRepeatKind === "once"
        ? null
        : eventRepeatKind === "weekly2"
          ? 2
          : eventRepeatKind === "weeklyCustom" ||
              eventRepeatKind === "monthlyCustom"
            ? Number(f.get("event_repeat_custom")) || null
            : 1;
    const eventMonthly = eventRepeatKind.startsWith("monthly");
    try {
      await api(
        editingEvent
          ? `/calendar/${editingEvent.id}?scope=${eventEditScope}`
          : "/calendar",
        {
        method: editingEvent ? "PUT" : "POST",
        body: JSON.stringify({
          title: f.get("title"),
          description: f.get("description") || null,
          starts_at: new Date(String(f.get("starts_at"))).toISOString(),
          ends_at: new Date(String(f.get("ends_at"))).toISOString(),
          all_day: false,
          category: "FAMILY",
          event_type: String(f.get("event_type")),
          custom_type_label: f.get("custom_type_label") || null,
          child_id: childlessEventTypes.has(eventType) ? null : Number(f.get("child_id")) || null,
          color: f.get("color"),
          is_private: false,
          // Sichtbarkeit ergibt sich aus Rubrik- und Kinderfreigaben.
          visible_to_user_ids: eventType === "PRIVATE" ? f.getAll("visible_to_user_ids").map(Number) : null,
          recurrence_frequency: eventInterval
            ? eventMonthly
              ? "MONTHLY"
              : "WEEKLY"
            : null,
          recurrence_interval: eventInterval,
          recurrence_day_of_month:
            eventRepeatKind === "monthlyDay"
              ? Number(f.get("event_recurrence_day")) || null
              : null,
          recurrence_until:
            eventInterval && f.get("event_until")
              ? new Date(String(f.get("event_until")) + "T23:59").toISOString()
              : null,
        }),
        },
      );
      if (stayToConvert) {
        await api(`/stays/${stayToConvert.id}?scope=${editScope}`, { method: "DELETE" });
      }
      setOpen(null);
      setEditingEvent(null);
      setStayToConvert(null);
      setSelectedDay(null);
      setEventRepeatKind("once");
      load();
    } catch (x) {
      setError((x as Error).message);
    }
  }
  async function deleteEvent() {
    if (!eventDeleteChoice) return;
    setError("");
    try {
      const scope = eventDeleteChoice.recurrence_group
        ? eventEditScope
        : "occurrence";
      await api(`/calendar/${eventDeleteChoice.id}?scope=${scope}`, {
        method: "DELETE",
      });
      setEventDeleteChoice(null);
      setEditingEvent(null);
      setOpen(null);
      load();
    } catch (x) {
      setError((x as Error).message);
    }
  }
  async function staySubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const repeat =
      repeatKind === "once"
        ? null
        : repeatKind === "weekly2"
          ? 2
          : repeatKind === "weekly3"
            ? 3
            : repeatKind === "weekly4"
              ? 4
              : repeatKind === "weeklyCustom" || repeatKind === "monthlyCustom"
                ? Number(f.get("repeat_custom")) || null
                : 1;
    const monthly = repeatKind.startsWith("monthly");
    try {
      const payload = {
        child_id: Number(f.get("child_id")),
        responsible_user_id: Number(f.get("responsible_user_id")),
        starts_at: new Date(String(f.get("starts_at"))).toISOString(),
        ends_at: new Date(String(f.get("ends_at"))).toISOString(),
        status: "CONFIRMED",
        note: f.get("note") || null,
        recurrence_interval_weeks: repeat,
        recurrence_frequency: monthly ? "MONTHLY" : "WEEKLY",
        recurrence_day_of_month:
          repeatKind === "monthlyDay"
            ? Number(f.get("recurrence_day_of_month")) || null
            : null,
        recurrence_until:
          repeat && f.get("until")
            ? new Date(String(f.get("until")) + "T23:59").toISOString()
            : null,
      };
      const stayToChange = editingStay;
      if (stayToChange) {
        const update = {
          starts_at: payload.starts_at,
          ends_at: payload.ends_at,
          responsible_user_id: payload.responsible_user_id,
          note: payload.note,
          scope: editScope,
          preserve_remainder: stayRangeMode === "day",
          ...(editScope === "series" && editingStay?.recurrence_rule_id
            ? {
                recurrence_interval_weeks: payload.recurrence_interval_weeks,
                recurrence_frequency: payload.recurrence_frequency,
                recurrence_day_of_month: payload.recurrence_day_of_month,
                recurrence_until: payload.recurrence_until,
              }
            : {}),
        };
        const isAdmin = getSessionUser()?.role === "ADMIN";
        if (isAdmin && !counterRequest) {
          setAdminChoice({ stayId: stayToChange.id, update });
          setOpen(null);
          return;
        }
        await api(
          counterRequest
            ? `/change-requests/${counterRequest.id}/decision`
            : isAdmin
              ? `/stays/${stayToChange.id}`
              : `/stays/${stayToChange.id}/proposals`,
          {
            method: counterRequest ? "POST" : isAdmin ? "PUT" : "POST",
            body: JSON.stringify(
              counterRequest
                ? { decision: "COUNTER", counter_proposal: update }
                : update,
            ),
          },
        );
      } else {
        if (getSessionUser()?.role === "ADMIN") {
          setAdminCreateChoice(payload);
          setOpen(null);
          return;
        }
        await api("/stay-proposals", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      }
      setOpen(null);
      setEditingStay(null);
      setCounterRequest(null);
      setCreateDraft(null);
      load();
    } catch (x) {
      setError((x as Error).message);
    }
  }
  function openCalendarEvent(
    event: CalendarEvent,
    scope: "occurrence" | "future" | "series" = "occurrence",
  ) {
    if (!canWriteCalendar || (event.event_type === "PRIVATE" && event.created_by_id !== getSessionUser()?.id)) {
      const start = new Date(event.starts_at), end = new Date(event.ends_at);
      setReadOnlyInfo({ title:event.title, message:`${start.toLocaleString("de-DE")} – ${end.toLocaleString("de-DE")}${event.description ? `\n\n${event.description}` : ""}\n\nDu besitzt Leserechte und kannst diesen Termin deshalb nicht bearbeiten.` });
      return;
    }
    const interval = event.recurrence_interval || 1;
    setEventRepeatKind(
      event.recurrence_frequency === "MONTHLY"
        ? interval === 1
          ? "monthlySame"
          : "monthlyCustom"
        : interval === 1
          ? "weekly1"
          : interval === 2
            ? "weekly2"
            : "weeklyCustom",
    );
    setEditingEvent(event);
    setEventType(event.event_type || "GENERAL");
    setEventEditScope(scope);
    setOpen("event");
    setError("");
  }
  function openDay(day: Date, dayStays: Stay[], selectedStay?: Stay) {
    const source = selectedStay || dayStays[0] || null;
    if (!canWriteCalendar) {
      if (source) setReadOnlyInfo({ title:`Betreuungszeit: ${children.find((child)=>child.id===source.child_id)?.display_name || "Kind"}`, message:`Bei ${source.responsible_display_name || "Person"}\n${new Date(source.starts_at).toLocaleString("de-DE")} – ${new Date(source.ends_at).toLocaleString("de-DE")}${source.note ? `\n\n${source.note}` : ""}\n\nDu besitzt Leserechte und kannst diese Betreuungszeit deshalb nicht bearbeiten.` });
      return;
    }
    const dayStart = new Date(day.getFullYear(), day.getMonth(), day.getDate());
    const dayEnd = new Date(
      day.getFullYear(),
      day.getMonth(),
      day.getDate() + 1,
    );
    setSelectedDay(day);
    setEditingStaySource(source);
    setStayRangeMode("full");
    setEditingStay(source);
    setCounterRequest(null);
    setEditScope("occurrence");
    setError("");
    setOpen("stay");
  }
  function changeStayRange(mode: "full" | "day") {
    setStayRangeMode(mode);
    if (!editingStaySource || !selectedDay) return;
    if (mode === "full") {
      setEditingStay(editingStaySource);
      return;
    }
    const dayStart = new Date(
      selectedDay.getFullYear(),
      selectedDay.getMonth(),
      selectedDay.getDate(),
    );
    const dayEnd = new Date(
      selectedDay.getFullYear(),
      selectedDay.getMonth(),
      selectedDay.getDate() + 1,
    );
    setEditingStay({
      ...editingStaySource,
      starts_at: new Date(
        Math.max(new Date(editingStaySource.starts_at).getTime(), dayStart.getTime()),
      ).toISOString(),
      ends_at: new Date(
        Math.min(new Date(editingStaySource.ends_at).getTime(), dayEnd.getTime()),
      ).toISOString(),
    });
  }
  async function decide(
    request: ChangeRequest,
    decision: "APPROVE" | "REJECT",
    comment?: string,
  ) {
    setError("");
    try {
      await api(`/change-requests/${request.id}/decision`, {
        method: "POST",
        body: JSON.stringify({ decision, comment }),
      });
      setRejectingRequest(null);
      load();
    } catch (x) {
      setError((x as Error).message);
    }
  }
  function openGroupReview(request: ChangeRequest) {
    setGroupReview(request);
    setGroupReviewItems((request.proposed_data.items || []).map((item) => ({ ...item })));
    setError("");
  }
  function updateGroupReview(index: number, change: Record<string, unknown>) {
    setGroupReviewItems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...change } : item));
  }
  async function decideGroup(decision: "APPROVE" | "REJECT" | "COUNTER") {
    if (!groupReview) return;
    if (decision === "REJECT" && !groupReviewItems.some((item) => item.comment?.trim())) {
      setError("Bitte hinterlasse bei mindestens einem Abschnitt eine Begründung.");
      return;
    }
    setGroupReviewBusy(true);
    setError("");
    try {
      await api(`/change-requests/${groupReview.id}/decision`, {
        method: "POST",
        body: JSON.stringify({
          decision,
          item_comments: Object.fromEntries(groupReviewItems.map((item, index) => [String(index + 1), item.comment || ""]).filter(([, comment]) => comment)),
          counter_proposal: decision === "COUNTER" ? {
            action: "GROUP_CREATE",
            title: groupReview.proposed_data.title,
            items: groupReviewItems.map(({ stay_id: _stayId, ...item }) => item),
          } : null,
        }),
      });
      setGroupReview(null);
      setGroupReviewItems([]);
      load();
    } catch (x) {
      setError((x as Error).message);
    } finally {
      setGroupReviewBusy(false);
    }
  }
  function openCounter(request: ChangeRequest) {
    const stay = stays.find((item) => item.id === request.object_id);
    if (
      !stay ||
      !request.proposed_data.starts_at ||
      !request.proposed_data.ends_at ||
      !request.proposed_data.responsible_user_id
    )
      return;
    setEditingStay({
      ...stay,
      starts_at: request.proposed_data.starts_at,
      ends_at: request.proposed_data.ends_at,
      responsible_user_id: request.proposed_data.responsible_user_id,
      note: request.proposed_data.note ?? null,
    });
    setCounterRequest(request);
    setError("");
    setOpen("stay");
  }
  function openSeries(stay: Stay) {
    if (!canWriteCalendar) return;
    const interval = stay.recurrence_interval_weeks || 1;
    setRepeatKind(
      stay.recurrence_frequency === "MONTHLY"
        ? interval === 1
          ? "monthlySame"
          : "monthlyCustom"
        : interval >= 1 && interval <= 4
          ? `weekly${interval}`
          : "weeklyCustom",
    );
    setEditingStay(stay);
    setSelectedDay(new Date(stay.starts_at));
    setCounterRequest(null);
    setEditScope("series");
    setError("");
    setOpen("stay");
  }
  async function applyAdminChange(asProposal: boolean) {
    if (!adminChoice) return;
    setError("");
    try {
      await api(
        asProposal
          ? `/stays/${adminChoice.stayId}/proposals`
          : `/stays/${adminChoice.stayId}`,
        {
          method: asProposal ? "POST" : "PUT",
          body: JSON.stringify(adminChoice.update),
        },
      );
      setAdminChoice(null);
      setEditingStay(null);
      load();
    } catch (x) {
      setError((x as Error).message);
    }
  }
  async function applyAdminCreate(asProposal: boolean) {
    if (!adminCreateChoice) return;
    setError("");
    try {
      await api(asProposal ? "/stay-proposals" : "/stays", {
        method: "POST",
        body: JSON.stringify(adminCreateChoice),
      });
      setAdminCreateChoice(null);
      setEditingStay(null);
      load();
    } catch (x) {
      setError((x as Error).message);
      api<Stay[]>("/stays/conflicts", {
        method: "POST",
        body: JSON.stringify(adminCreateChoice),
      })
        .then(setCreateConflicts)
        .catch(() => setCreateConflicts([]));
    }
  }
  async function removeStay() {
    if (!editingStay) return;
    if (getSessionUser()?.role === "ADMIN") {
      setAdminDeleteChoice({ stayId: editingStay.id, scope: editScope });
      setOpen(null);
      setError("");
      return;
    }
    const label =
      editScope === "series"
        ? "die gesamte Serie"
        : editScope === "future"
          ? "diesen und alle zukünftigen Termine"
          : "diese Betreuungszeit";
    setDeleteProposalChoice({
      stayId: editingStay.id,
      scope: editScope,
      label,
    });
    setOpen(null);
  }
  async function sendDeletionProposal() {
    if (!deleteProposalChoice) return;
    setError("");
    try {
      await api(
        `/stays/${deleteProposalChoice.stayId}/deletion-proposals?scope=${deleteProposalChoice.scope}`,
        { method: "POST" },
      );
      setDeleteProposalChoice(null);
      setEditingStay(null);
      load();
    } catch (x) {
      setError((x as Error).message);
    }
  }
  async function applyAdminDeletion(asProposal: boolean) {
    if (!adminDeleteChoice) return;
    setError("");
    try {
      await api(
        asProposal
          ? `/stays/${adminDeleteChoice.stayId}/deletion-proposals?scope=${adminDeleteChoice.scope}`
          : `/stays/${adminDeleteChoice.stayId}?scope=${adminDeleteChoice.scope}`,
        { method: asProposal ? "POST" : "DELETE" },
      );
      setAdminDeleteChoice(null);
      setEditingStay(null);
      load();
    } catch (x) {
      setError((x as Error).message);
    }
  }
  return (
    <>
      <header className="pagehead">
        <div>
          <span className="eyebrow">Planung</span>
          <h1>Kalender</h1>
          <p>Alle Einträge als Termine mit passender Terminart planen.</p>
        </div>
      </header>
      {requests.length > 0 && (
        <section className="change-requests">
          <h2>Offene Abstimmungen</h2>
          {error && !open && <p className="error">{error}</p>}
          {requests.map((request) => {
            const proposal = request.proposed_data;
            const before = request.before_data;
            const canDecide = getSessionUser()?.id === request.affected_user_id;
            const scopeLabel =
              proposal.scope === "series"
                ? "gesamte Serie"
                : proposal.scope === "future"
                  ? "dieser und alle zukünftigen Termine"
                  : "einzelne Betreuungszeit";
            const previousPerson = people.find(
              (person) => person.id === before.responsible_user_id,
            );
            const proposedPerson = people.find(
              (person) => person.id === proposal.responsible_user_id,
            );
            return (
              <article key={request.id} id={`planning-request-${request.id}`}>
                <div>
                  <strong>{request.requested_by_name}</strong>{" "}
                  {proposal.action === "GROUP_CREATE" ? (
                    <>
                      sendet die Gruppenplanung „{proposal.title || "Gemeinsame Planung"}“.
                      <div className="grouprequestitems">
                        {(proposal.items || []).map((item, index) => (
                          <span key={item.stay_id || index}>
                            <b>{item.name}</b> · {children.find((child) => child.id === item.child_id)?.display_name || "Kind"} bei {people.find((person) => person.id === item.responsible_user_id)?.display_name || "unbekannt"} · {new Date(item.starts_at).toLocaleDateString("de-DE")} – {new Date(new Date(item.ends_at).getTime() - 1).toLocaleDateString("de-DE")}
                          </span>
                        ))}
                      </div>
                    </>
                  ) : proposal.action === "DELETE" ? (
                    <>
                      schlägt die Löschung einer Betreuungszeit vor.
                      <small>
                        {request.child_name || "Kind"} · bisher bei{" "}
                        {previousPerson?.display_name || "unbekannt"} ·{" "}
                        {before.starts_at
                          ? new Date(before.starts_at).toLocaleString("de-DE")
                          : ""}{" "}
                        –{" "}
                        {before.ends_at
                          ? new Date(before.ends_at).toLocaleString("de-DE")
                          : ""}{" "}
                        · {scopeLabel}
                      </small>
                    </>
                  ) : proposal.action === "CREATE" ? (
                    <>
                      schlägt eine neue Betreuungszeit bei{" "}
                      <strong>
                        {proposedPerson?.display_name || "unbekannt"}
                      </strong>{" "}
                      vor.
                      <small>
                        {new Date(proposal.starts_at!).toLocaleString("de-DE")}{" "}
                        – {new Date(proposal.ends_at!).toLocaleString("de-DE")}
                        {proposal.recurrence_interval_weeks
                          ? ` · Periodisch alle ${proposal.recurrence_interval_weeks} ${proposal.recurrence_interval_weeks === 1 ? "Woche" : "Wochen"}${proposal.recurrence_until ? ` bis ${new Date(proposal.recurrence_until).toLocaleDateString("de-DE")}` : ""}`
                          : ""}
                      </small>
                    </>
                  ) : (
                    <>
                      schlägt eine Änderung vor.
                      <small className="change-comparison">
                        <b>{request.child_name || "Kind"}</b>
                        {before.responsible_user_id !==
                          proposal.responsible_user_id && (
                          <span>
                            Person: {previousPerson?.display_name || "unbekannt"}{" "}
                            → {proposedPerson?.display_name || "unbekannt"}
                          </span>
                        )}
                        {(before.starts_at !== proposal.starts_at ||
                          before.ends_at !== proposal.ends_at) && (
                          <span>
                            Zeitraum:{" "}
                            {new Date(before.starts_at!).toLocaleString("de-DE")}{" "}
                            – {new Date(before.ends_at!).toLocaleString("de-DE")}{" "}
                            →{" "}
                            {new Date(proposal.starts_at!).toLocaleString(
                              "de-DE",
                            )}{" "}
                            –{" "}
                            {new Date(proposal.ends_at!).toLocaleString("de-DE")}
                          </span>
                        )}
                        {before.note !== proposal.note && (
                          <span>
                            Notiz: {before.note || "–"} → {proposal.note || "–"}
                          </span>
                        )}
                        <span>Umfang: {scopeLabel}</span>
                      </small>
                    </>
                  )}
                </div>
                {proposal.action === "GROUP_CREATE" ? (
                  <div className="request-actions">
                    <button onClick={() => openGroupReview(request)}>
                      {canDecide ? "Planung prüfen" : "Details ansehen"}
                    </button>
                    {!canDecide && <span className="tag">Wartet auf {request.affected_user_name}</span>}
                  </div>
                ) : canDecide ? (
                  <div className="request-actions">
                    <button onClick={() => decide(request, "APPROVE")}>
                      Bestätigen
                    </button>
                    {proposal.action !== "DELETE" && (
                      <button
                        className="secondary"
                        onClick={() => openCounter(request)}
                      >
                        Gegenvorschlag
                      </button>
                    )}
                    <button
                      className="secondary danger"
                      onClick={() => setRejectingRequest(request)}
                    >
                      Ablehnen
                    </button>
                  </div>
                ) : (
                  <span className="tag">
                    Wartet auf {request.affected_user_name}
                  </span>
                )}
              </article>
            );
          })}
        </section>
      )}
      <div className="calendar-content">
      {(series.length > 0 || eventSeries.length > 0) && (
        <details className="series-list calendar-collapsible">
          <summary>Periodische Einträge</summary>
          <p>Regelmäßige Betreuungszeiten und Terminserien unabhängig vom angezeigten Monat verwalten.</p>
          {series.map((stay) => (
            <article key={stay.recurrence_rule_id}>
              <div>
                <strong>
                  {stay.note || "Unbenannte Serie"} ·{" "}
                  {
                    children.find((child) => child.id === stay.child_id)
                      ?.display_name
                  }{" "}
                  bei {stay.responsible_display_name}
                </strong>
                <small>
                  {stay.recurrence_frequency === "MONTHLY"
                    ? stay.recurrence_interval_weeks === 1
                      ? "Jeden Monat"
                      : `Alle ${stay.recurrence_interval_weeks} Monate`
                    : stay.recurrence_interval_weeks === 1
                      ? "Jede Woche"
                      : `Alle ${stay.recurrence_interval_weeks} Wochen`}{" "}
                  · bis{" "}
                  {stay.recurrence_until
                    ? new Date(stay.recurrence_until).toLocaleDateString(
                        "de-DE",
                      )
                    : "ohne Enddatum"}{" "}
                  · Beginn: {new Date(stay.starts_at).toLocaleString("de-DE")}
                </small>
              </div>
              {canWriteCalendar && <button onClick={() => openSeries(stay)}>Betreuungsserie bearbeiten</button>}
            </article>
          ))}
          {eventSeries.map((event) => (
            <article key={`event-series-${event.recurrence_group}`}>
              <div>
                <strong>
                  {event.title}
                </strong>
                <small>
                  {event.recurrence_frequency === "MONTHLY"
                    ? event.recurrence_interval === 1
                      ? "Jeden Monat"
                      : `Alle ${event.recurrence_interval} Monate`
                    : event.recurrence_interval === 1
                      ? "Jede Woche"
                      : `Alle ${event.recurrence_interval} Wochen`} · bis{" "}
                  {event.recurrence_until
                    ? new Date(event.recurrence_until).toLocaleDateString("de-DE")
                    : "ohne Enddatum"} · Beginn:{" "}
                  {new Date(event.starts_at).toLocaleString("de-DE")}
                </small>
              </div>
              {canWriteCalendar && (event.created_by_id === getSessionUser()?.id || (event.event_type !== "PRIVATE" && getSessionUser()?.role === "ADMIN")) && <button onClick={() => openCalendarEvent(event, "series")}>
                Terminserie bearbeiten
              </button>}
            </article>
          ))}
        </details>
      )}
      <details className="calendar-type-filters calendar-collapsible" aria-label="Angezeigte Terminarten">
        <summary>Terminarten ein- und ausblenden</summary>
        <div className="calendar-filter-options">
        {availableEventTypes.map((type) => (
          <label key={type} className={`event-type-chip${hiddenEventTypes.includes(type)?" muted-chip":""}`} style={{"--chip-color":eventTypeDisplayColor(type)} as React.CSSProperties}>
            <input type="checkbox" checked={!hiddenEventTypes.includes(type)} onChange={() => setHiddenEventTypes((current) => {
              const changed = current.includes(type) ? current.filter((item) => item !== type) : [...current, type];
              localStorage.setItem("familienplan-calendar-hidden-types", JSON.stringify(changed));
              return changed;
            })}/>
            <span>{eventTypeLabels[type]}</span>
          </label>
        ))}
        </div>
      </details>
      <section className={`monthcalendar${canWriteCalendar ? "" : " calendar-readonly"}`}>
        <header className="calendar-navigation">
          <button
            onClick={() =>
              setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))
            }
            aria-label="Vorheriger Monat"
          >
            <ChevronLeft />
          </button>
          <h2>
            {month.toLocaleDateString("de-DE", {
              month: "long",
              year: "numeric",
            })}
          </h2>
          <button
            onClick={() =>
              setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))
            }
            aria-label="Nächster Monat"
          >
            <ChevronRight />
          </button>
          {canWriteCalendar && <button className="calendar-create" onClick={() => { setEditingEvent(null); setStayToConvert(null); setEventType("GENERAL"); setEventRepeatKind("once"); setSelectedDay(null); setOpen("event"); }}><Plus size={18}/> Termin anlegen</button>}
        </header>
        <div className="weekdays">
          {["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"].map((day) => (
            <span key={day}>{day}</span>
          ))}
        </div>
        <div className="monthgrid">
          {days.map((day) => {
            const dayEnd = new Date(
              day.getFullYear(),
              day.getMonth(),
              day.getDate() + 1,
            );
            const dayStays = stays.filter(
              (stay) =>
                new Date(stay.starts_at) < dayEnd &&
                new Date(stay.ends_at) > day,
            );
            const dayEvents = events.filter(
              (event) =>
                !hiddenEventTypes.includes(event.event_type) &&
                calendarEventOccursOnDay(event, day, dayEnd),
            );
            const duplicateEventIds = new Set(
              dayEvents
                .filter((event) => dayEvents.some((other) =>
                  other.id !== event.id &&
                  Boolean(other.source_id) !== Boolean(event.source_id) &&
                  other.event_type === event.event_type &&
                  other.title.trim().toLocaleLowerCase("de-DE") === event.title.trim().toLocaleLowerCase("de-DE"),
                ))
                .map((event) => event.id),
            );
            const dayHolidays = holidays.filter(
              (holiday) =>
                new Date(`${holiday.starts_on}T00:00:00`) < dayEnd &&
                new Date(`${holiday.ends_on}T23:59:59`) >= day,
            );
            const birthdays = !availableEventTypes.includes("BIRTHDAY") || hiddenEventTypes.includes("BIRTHDAY") ? [] : [
              ...children
                .filter((child) => child.birth_date)
                .map((child) => ({
                  id: `child-${child.id}`,
                  name: child.display_name,
                  birthDate: child.birth_date!,
                  isPrivate: false,
                })),
              ...people
                .filter((person) => person.birth_date)
                .map((person) => ({
                  id: `person-${person.id}`,
                  name: person.display_name,
                  birthDate: person.birth_date!,
                  isPrivate: false,
                })),
              ...customBirthdays.map((birthday) => ({
                id: `birthday-${birthday.id}`,
                name: birthday.display_name,
                birthDate: birthday.birth_date,
                isPrivate: birthday.is_private,
                eventType: birthday.event_type,
              })),
            ]
              .filter((birthday) => {
                const birthDate = new Date(`${birthday.birthDate}T00:00:00`);
                return (
                  day.getFullYear() >= birthDate.getFullYear() &&
                  birthDate.getMonth() === day.getMonth() &&
                  birthDate.getDate() === day.getDate()
                );
              })
              .map((birthday) => ({
                ...birthday,
                age:
                  day.getFullYear() -
                  new Date(`${birthday.birthDate}T00:00:00`).getFullYear(),
              }));
            const isToday = day.toDateString() === now.toDateString();
            return (
              <article
                className={`${day.getMonth() !== month.getMonth() ? "outside " : ""}${isToday ? "todaycell " : ""}${dayHolidays.length ? "holidaycell" : ""}`}
                key={day.toISOString()}
                onClick={(event) => {
                  if ((event.target as HTMLElement).closest(".dayevent")) return;
                  if (!canWriteCalendar) return;
                  setSelectedDay(day);
                  setEditingEvent(null);
                  setEventType("GENERAL");
                  setEventRepeatKind("once");
                  setError("");
                  setOpen("event");
                }}
                title={canWriteCalendar ? "Termin an diesem Tag anlegen" : undefined}
                style={dayEvents.some((event) => event.event_type === "WASTE") ? {
                  backgroundColor: "color-mix(in srgb, var(--waste) 9%, white)",
                } : undefined}
              >
                <time>{day.getDate()}</time>
                <div className="dayentries">
                  {availableEventTypes.includes("STAY") && !hiddenEventTypes.includes("STAY") && children.map((child) => {
                    const childStays = dayStays
                      .filter((item) => item.child_id === child.id)
                      .sort((a, b) => a.starts_at.localeCompare(b.starts_at));
                    if (childStays.length) {
                      return childStays.map((stay) => {
                        const responsible = people.find(
                          (person) => person.id === stay.responsible_user_id,
                        );
                        if (!responsible) return null;
                        const conflictingStay = childStays.find(
                          (other) =>
                            other.id !== stay.id &&
                            other.responsible_user_id !==
                              stay.responsible_user_id &&
                            new Date(other.starts_at) <
                              new Date(stay.ends_at) &&
                            new Date(other.ends_at) >
                              new Date(stay.starts_at),
                        );
                        const visibleStart = new Date(
                          Math.max(
                            new Date(stay.starts_at).getTime(),
                            day.getTime(),
                          ),
                        );
                        const visibleEnd = new Date(
                          Math.min(
                            new Date(stay.ends_at).getTime(),
                            dayEnd.getTime(),
                          ),
                        );
                        const showTime =
                          childStays.length > 1 ||
                          visibleStart.getTime() > day.getTime() ||
                          visibleEnd.getTime() < dayEnd.getTime();
                        const timeLabel = showTime
                          ? `${visibleStart.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}–${visibleEnd.getTime() === dayEnd.getTime() ? "24:00" : visibleEnd.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}`
                          : "";
                        return (
                          <span
                            className={`daystay exception${conflictingStay ? " stay-conflict" : ""}${target?.kind === "stay" && [target.id, ...(target.relatedIds || [])].includes(stay.id) ? " calendar-highlight" : ""}`}
                            key={`child-${child.id}-stay-${stay.id}`}
                            data-calendar-target={`stay-${stay.id}`}
                            title={
                              conflictingStay
                                ? `Konflikt: gleichzeitig bei ${conflictingStay.responsible_display_name || "einer anderen Person"}`
                                : stay.note || undefined
                            }
                            style={{
                              backgroundColor: `color-mix(in srgb, ${responsible.color} 30%, white)`,
                              color: `color-mix(in srgb, ${responsible.color} 65%, #172d27)`,
                              borderLeftColor: responsible.color,
                            }}
                            onClick={(event) => {
                              event.stopPropagation();
                              openDay(day, dayStays, stay);
                            }}
                          >
                            <CareMarkers child={child} responsible={responsible} />
                            <b>{child.display_name}</b> bei{" "}
                            {responsible.display_name}
                            {stay.note ? ` · ${stay.note}` : ""}
                            {conflictingStay && (
                              <em className="conflict-badge">Konflikt</em>
                            )}
                            {timeLabel && <small>{timeLabel}</small>}
                          </span>
                        );
                      });
                    }
                    const responsible = people.find(
                      (person) =>
                        person.id === child.default_responsible_user_id,
                    );
                    return responsible ? (
                      <span
                        className="daystay"
                        key={`child-${child.id}-default`}
                        style={{
                          backgroundColor: `color-mix(in srgb, ${responsible.color} 16%, white)`,
                          color: `color-mix(in srgb, ${responsible.color} 65%, #172d27)`,
                          borderLeftColor: responsible.color,
                        }}
                        onClick={(event) => {
                          event.stopPropagation();
                          if (!canWriteCalendar) {
                            setReadOnlyInfo({ title:`Betreuung: ${child.display_name}`, message:`Standardmäßig bei ${responsible.display_name}.\n\nDies ist die hinterlegte Standardbetreuung und kein einzeln gespeicherter Termin.` });
                            return;
                          }
                          const startsAt = new Date(day);
                          const endsAt = new Date(dayEnd);
                          setCreateDraft({
                            child_id: child.id,
                            responsible_user_id: responsible.id,
                            starts_at: startsAt.toISOString(),
                            ends_at: endsAt.toISOString(),
                            note: null,
                          });
                          setSelectedDay(day);
                          setEditingStay(null);
                          setRepeatKind("once");
                          setOpen("stay");
                        }}
                      >
                        <CareMarkers child={child} responsible={responsible} />
                        <b>{child.display_name}</b> bei{" "}
                        {responsible.display_name}
                      </span>
                    ) : null;
                  })}
                  {dayEvents.map((event) => (
                    <span
                      className={`dayevent${event.child_id ? " has-child-marker" : ""}${target?.kind === "event" && target.id === event.id ? " calendar-highlight" : ""}`}
                      key={`event-${event.id}`}
                      data-calendar-target={`event-${event.id}`}
                      style={{
                        backgroundColor: `color-mix(in srgb, ${eventDisplayColor(event)} 20%, white)`,
                        color: `color-mix(in srgb, ${eventDisplayColor(event)} 70%, #172d27)`,
                        borderLeft: `3px solid ${eventDisplayColor(event)}`,
                      }}
                      title={event.event_type === "PRIVATE" ? ((event.visible_to_user_ids?.length || 0) > 1 ? "Privater Termin · für ausgewählte Personen sichtbar" : "Privater Termin · nur für mich sichtbar") : undefined}
                      onClick={(clickEvent) => {
                        clickEvent.stopPropagation();
                        if (event.source_id) {
                          const timing = calendarEventTiming(event);
                          const details = event.description?.trim() ? `\n\n${event.description.trim()}` : "";
                          setReadOnlyInfo({
                            title: event.title,
                            message: `${timing}${details}\n\n${event.event_type === "WASTE"
                              ? "Dieser Termin wurde aus dem externen Abfallkalender übernommen. Änderungen erfolgen an der Onlinequelle oder über die Einrichtung des Abfallkalenders."
                              : event.event_type === "SCHOOL"
                                ? "Dieser Termin wurde aus dem Schulkalender übernommen. Änderungen erfolgen an der Onlinequelle der Schule."
                                : "Dieser Termin wurde aus einer externen Kalenderquelle übernommen und kann hier nicht bearbeitet werden."}`,
                          });
                        } else openCalendarEvent(event);
                      }}
                      onPointerDown={(pointerEvent) =>
                        pointerEvent.stopPropagation()
                      }
                    >
                      {event.child_id && children.find((child) => child.id === event.child_id) && <ChildStar child={children.find((child) => child.id === event.child_id)!} />}
                      {event.title}
                      {duplicateEventIds.has(event.id) ? " · Mögliche Dublette" : ""}
                      {!event.source_id && event.description?.trim() && <small className="event-note">{event.description.trim()}</small>}
                      {calendarEventTimeOnDay(event, day, dayEnd) && <small>{calendarEventTimeOnDay(event, day, dayEnd)}</small>}
                    </span>
                  ))}
                  {birthdays.map((birthday) => (
                    <span
                      className={`daybirthday${target?.kind === "birthday" && birthday.id === `birthday-${target.id}` ? " calendar-highlight" : ""}`}
                      key={birthday.id}
                      data-calendar-target={birthday.id.startsWith("birthday-") ? birthday.id : undefined}
                      style={{
                        backgroundColor: "color-mix(in srgb, var(--birthday) 24%, white)",
                        borderLeftColor: "var(--birthday)",
                        color: "color-mix(in srgb, var(--birthday) 70%, #332b18)",
                      }}
                      title="Automatisch erzeugter Termin · Geburtstag"
                      onClick={(event) => {
                        event.stopPropagation();
                        setReadOnlyInfo({ title: `Geburtstag von ${birthday.name}`, message: "Dieser Geburtstag wird automatisch aus den Personendaten erzeugt und kann deshalb nicht direkt im Kalender bearbeitet werden. Ändere ihn in der jeweiligen Person, beim Kind oder in der Rubrik Geburtstage." });
                      }}
                    >
                      🎂 {birthday.name} wird {birthday.age}
                    </span>
                  ))}
                  {dayHolidays.map((holiday) => (
                    <span
                      className="dayholiday"
                      key={`${holiday.state}-${holiday.name}`}
                      title={holiday.name}
                      onClick={(event) => {
                        event.stopPropagation();
                        setReadOnlyInfo({ title: holiday.name, message: "Dieser Ferienzeitraum wird automatisch anhand des hinterlegten Bundeslandes erzeugt und kann nicht direkt im Kalender bearbeitet werden." });
                      }}
                    >
                      Ferien ·{" "}
                      {children
                        .filter(
                          (child) => child.school_state_code === holiday.state,
                        )
                        .map((child) => child.display_name)
                        .join(", ")}
                    </span>
                  ))}
                </div>
              </article>
            );
          })}
        </div>
        <div className="weekdays weekdays-bottom" aria-label="Wochentage">
          {["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"].map((day) => (
            <span key={`bottom-${day}`}>{day}</span>
          ))}
        </div>
        <footer className="calendar-navigation calendar-footer-nav">
          <button onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))} aria-label="Vorheriger Monat"><ChevronLeft /></button>
          <h2>{month.toLocaleDateString("de-DE", { month: "long", year: "numeric" })}</h2>
          <button onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))} aria-label="Nächster Monat"><ChevronRight /></button>
          {canWriteCalendar && <button className="calendar-create" onClick={() => { setEditingEvent(null); setStayToConvert(null); setEventType("GENERAL"); setEventRepeatKind("once"); setSelectedDay(null); setOpen("event"); }}><Plus size={18}/> Termin anlegen</button>}
        </footer>
      </section>
      </div>
      {readOnlyInfo && <div className="modal confirmmodal" role="dialog" aria-modal="true"><section className="panel"><button type="button" className="close" onClick={() => setReadOnlyInfo(null)} aria-label="Schließen">×</button><h2>{readOnlyInfo.title}</h2><p className="readonly-details">{readOnlyInfo.message}</p><div className="modalactions"><button type="button" onClick={() => setReadOnlyInfo(null)}>Verstanden</button></div></section></div>}
      {open && (
        <div className="modal">
          <form
            className="panel"
            onSubmit={open === "event" ? eventSubmit : staySubmit}
          >
            <button
              type="button"
              className="close"
              onClick={() => {
                setOpen(null);
                setEditingEvent(null);
                setStayToConvert(null);
                setEditingStaySource(null);
                setSelectedDay(null);
                setCounterRequest(null);
              }}
            >
              ×
            </button>
            <h2>{open === "stay" ? (editingStay ? "Betreuungszeit bearbeiten" : "Betreuungszeit eintragen") : (editingEvent || stayToConvert ? "Termin bearbeiten" : "Termin eintragen")}</h2>
            {error && <p className="error">{error}</p>}
            {open === "event" ? (
              <>
                <Field
                  label="Titel"
                  name="title"
                  defaultValue={editingEvent?.title || stayToConvert?.note || (stayToConvert ? `${children.find((child) => child.id === stayToConvert.child_id)?.display_name || "Kind"} bei ${stayToConvert.responsible_display_name || "Person"}` : "")}
                />
                <label>
                  Terminart
                  <select
                    name="event_type"
                    value={eventType}
                    onChange={(e) => {
                      const type = e.target.value as EventType;
                      if (type === "STAY") {
                        setEditingStay(null);
                        setEditingStaySource(null);
                        setStayRangeMode("full");
                        setCounterRequest(null);
                        setCreateDraft(null);
                        setRepeatKind("once");
                        setOpen("stay");
                      } else {
                        setEventType(type);
                      }
                    }}
                  >
                    {availableEventTypes.map((type) => (
                      <option key={type} value={type}>{eventTypeLabels[type as EventType]}</option>
                    ))}
                  </select>
                </label>
                {eventType === "OTHER" && (
                  <Field
                    label="Bezeichnung für Sonstiges"
                    name="custom_type_label"
                    defaultValue={editingEvent?.custom_type_label || ""}
                  />
                )}
                {eventType === "PRIVATE" && (
                  <AudiencePicker
                    key={`private-event-audience-${editingEvent?.id || "new"}`}
                    people={people}
                    initialValues={editingEvent?.event_type === "PRIVATE" ? editingEvent.visible_to_user_ids : []}
                    privateDefault
                  />
                )}
                {!childlessEventTypes.has(eventType) && <label>
                    Kind (optional)
                    <select
                      name="child_id"
                      defaultValue={editingEvent?.child_id || stayToConvert?.child_id || ""}
                    >
                      <option value="">Kein Kind</option>
                      {children.map((c) => (
                        <option value={c.id}>{c.display_name}</option>
                      ))}
                    </select>
                  </label>}
                <div className="grid2">
                  <Field
                    label="Beginn"
                    name="starts_at"
                    type="datetime-local"
                    defaultValue={localDateTime(
                      editingEvent
                        ? new Date(editingEvent.starts_at)
                        : stayToConvert
                          ? new Date(stayToConvert.starts_at)
                        : selectedDay || now,
                    )}
                  />
                  <Field
                    label="Ende"
                    name="ends_at"
                    type="datetime-local"
                    defaultValue={localDateTime(
                      editingEvent
                        ? new Date(editingEvent.ends_at)
                        : stayToConvert
                          ? new Date(stayToConvert.ends_at)
                        : new Date((selectedDay || now).getTime() + 3600000),
                    )}
                  />
                </div>
                <Field
                  label="Notiz"
                  name="description"
                  required={false}
                  defaultValue={editingEvent?.description || stayToConvert?.note || ""}
                />
                <label>
                  Farbe
                  <input
                    name="color"
                    type="color"
                    defaultValue={editingEvent?.color || people.find((person) => person.id === stayToConvert?.responsible_user_id)?.color || getSessionUser()?.color || "#8B6CC1"}
                  />
                </label>
                {(!editingEvent || editingEvent.recurrence_group) && <label>
                  Wiederholung
                  <select
                    value={eventRepeatKind}
                    onChange={(event) => setEventRepeatKind(event.target.value)}
                  >
                    <option value="once">Einmalig</option>
                    <option value="weekly1">Jede Woche</option>
                    <option value="weekly2">Alle zwei Wochen</option>
                    <option value="weeklyCustom">Alle X Wochen</option>
                    <option value="monthlySame">Jeden Monat am gleichen Tag</option>
                    <option value="monthlyDay">Jeden Monat am X. Tag</option>
                    <option value="monthlyCustom">Alle X Monate</option>
                  </select>
                </label>}
                {(!editingEvent || editingEvent.recurrence_group) && (eventRepeatKind === "weeklyCustom" ||
                  eventRepeatKind === "monthlyCustom") && (
                  <Field
                    label={
                      eventRepeatKind === "monthlyCustom"
                        ? "Abstand in Monaten"
                        : "Abstand in Wochen"
                    }
                    name="event_repeat_custom"
                    type="number"
                    defaultValue={editingEvent?.recurrence_interval?.toString() || stayToConvert?.recurrence_interval_weeks?.toString() || ""}
                  />
                )}
                {(!editingEvent || editingEvent.recurrence_group) && eventRepeatKind === "monthlyDay" && (
                  <Field
                    label="Tag im Monat (1–31)"
                    name="event_recurrence_day"
                    type="number"
                  />
                )}
                {(!editingEvent || editingEvent.recurrence_group) && eventRepeatKind !== "once" && (
                  <Field
                    label="Wiederholen bis (leer = ohne Ende)"
                    name="event_until"
                    type="date"
                    required={false}
                    defaultValue={
                      editingEvent?.recurrence_until
                        ? editingEvent.recurrence_until.slice(0, 10)
                        : stayToConvert?.recurrence_until
                          ? stayToConvert.recurrence_until.slice(0, 10)
                        : ""
                    }
                  />
                )}
                {editingEvent?.recurrence_group && (
                  <label>
                    Änderung anwenden auf
                    <select
                      value={eventEditScope}
                      onChange={(event) =>
                        setEventEditScope(
                          event.target.value as typeof eventEditScope,
                        )
                      }
                    >
                      <option value="occurrence">Nur diesen Termin</option>
                      <option value="future">
                        Diesen und alle zukünftigen Termine
                      </option>
                      <option value="series">Gesamte Serie</option>
                    </select>
                  </label>
                )}
              </>
            ) : (
              <>
                <label>
                  Terminart
                  <select
                    value="STAY"
                    disabled={!!editingStay && getSessionUser()?.role !== "ADMIN"}
                    onChange={(event) => {
                      const type = event.target.value as EventType;
                      if (type !== "STAY") {
                        setStayToConvert(editingStay);
                        setEventType(type);
                        if (editingStay?.recurrence_rule_id) {
                          setEventRepeatKind(
                            editingStay.recurrence_frequency === "MONTHLY"
                              ? editingStay.recurrence_interval_weeks === 1 ? "monthlySame" : "monthlyCustom"
                              : editingStay.recurrence_interval_weeks === 1 ? "weekly1" : editingStay.recurrence_interval_weeks === 2 ? "weekly2" : "weeklyCustom",
                          );
                        }
                        setEditingStay(null);
                        setEditingStaySource(null);
                        setOpen("event");
                      }
                    }}
                  >
                    {availableEventTypes.map((type) => (
                      <option key={type} value={type}>{eventTypeLabels[type as EventType]}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Kind
                  <select
                    name="child_id"
                    required
                    defaultValue={
                      editingStay?.child_id ||
                      Number(createDraft?.child_id) ||
                      undefined
                    }
                  >
                    {children.map((c) => (
                      <option value={c.id}>{c.display_name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Das Kind ist bei
                  <select
                    name="responsible_user_id"
                    required
                    defaultValue={
                      editingStay?.responsible_user_id ||
                      Number(createDraft?.responsible_user_id) ||
                      undefined
                    }
                  >
                    {people.map((p) => (
                      <option value={p.id}>{p.display_name}</option>
                    ))}
                  </select>
                </label>
                {editingStaySource && selectedDay &&
                  new Date(editingStaySource.starts_at).toDateString() !==
                    new Date(
                      new Date(editingStaySource.ends_at).getTime() - 1,
                    ).toDateString() && (
                    <label>
                      Zeitraum bearbeiten
                      <select
                        value={stayRangeMode}
                        onChange={(event) =>
                          changeStayRange(
                            event.target.value as "full" | "day",
                          )
                        }
                      >
                        <option value="full">
                          Gesamter Zeitraum (
                          {new Date(
                            editingStaySource.starts_at,
                          ).toLocaleString("de-DE")} – {" "}
                          {new Date(
                            editingStaySource.ends_at,
                          ).toLocaleString("de-DE")})
                        </option>
                        <option value="day">
                          Nur {selectedDay.toLocaleDateString("de-DE")} (Rest des Zeitraums erhalten)
                        </option>
                      </select>
                    </label>
                  )}
                <div className="grid2">
                  <Field
                    key={`stay-start-${editingStay?.starts_at || "new"}`}
                    label="Von"
                    name="starts_at"
                    type="datetime-local"
                    defaultValue={localDateTime(
                      editingStay
                        ? new Date(editingStay.starts_at)
                        : createDraft?.starts_at
                          ? new Date(String(createDraft.starts_at))
                          : selectedDay || now,
                    )}
                  />
                  <Field
                    key={`stay-end-${editingStay?.ends_at || "new"}`}
                    label="Bis"
                    name="ends_at"
                    type="datetime-local"
                    defaultValue={localDateTime(
                      editingStay
                        ? new Date(editingStay.ends_at)
                        : createDraft?.ends_at
                          ? new Date(String(createDraft.ends_at))
                          : new Date((selectedDay || now).getTime() + 86400000),
                    )}
                  />
                </div>
                {(!editingStay ||
                  (editingStay.recurrence_rule_id &&
                    editScope === "series")) && (
                  <label>
                    Wiederholung
                    <select
                      value={repeatKind}
                      onChange={(event) => setRepeatKind(event.target.value)}
                    >
                      {!editingStay && <option value="once">Einmalig</option>}
                      <option value="weekly1">Jede Woche</option>
                      <option value="weekly2">Alle zwei Wochen</option>
                      <option value="weekly3">Alle drei Wochen</option>
                      <option value="weekly4">Alle vier Wochen</option>
                      <option value="weeklyCustom">Alle X Wochen</option>
                      <option value="monthlySame">
                        Jeden Monat am gleichen Tag
                      </option>
                      <option value="monthlyDay">Jeden Monat am X. Tag</option>
                      <option value="monthlyCustom">Alle X Monate</option>
                    </select>
                  </label>
                )}
                {(!editingStay || editScope === "series") &&
                  repeatKind === "monthlyDay" && (
                  <Field
                    label="Tag im Monat (1–31)"
                    name="recurrence_day_of_month"
                    type="number"
                    required={false}
                    defaultValue={
                      editingStay?.recurrence_day_of_month?.toString() || ""
                    }
                  />
                )}
                {(!editingStay || editScope === "series") &&
                  (repeatKind === "weeklyCustom" ||
                    repeatKind === "monthlyCustom") && (
                    <Field
                      label={
                        repeatKind === "monthlyCustom"
                          ? "Abstand in Monaten"
                          : "Abstand in Wochen"
                      }
                      name="repeat_custom"
                      type="number"
                      required={false}
                      defaultValue={
                        editingStay?.recurrence_interval_weeks?.toString() ||
                        ""
                      }
                    />
                  )}
                {(!editingStay || editScope === "series") &&
                  repeatKind !== "once" && (
                  <Field
                    label="Wiederholen bis (leer = ohne Ende)"
                    name="until"
                    type="date"
                    required={false}
                    defaultValue={
                      editingStay?.recurrence_until
                        ? String(editingStay.recurrence_until).slice(0, 10)
                        : createDraft?.recurrence_until
                        ? String(createDraft.recurrence_until).slice(0, 10)
                        : ""
                    }
                  />
                )}
                {editingStay?.recurrence_rule_id && (
                  <label>
                    Änderung anwenden auf
                    <select
                      name="scope"
                      value={editScope}
                      onChange={(event) =>
                        setEditScope(event.target.value as typeof editScope)
                      }
                    >
                      <option value="occurrence">Nur diesen Termin</option>
                      <option value="future">
                        Diesen und alle zukünftigen
                      </option>
                      <option value="series">Gesamte Serie</option>
                    </select>
                  </label>
                )}
                <Field
                  label="Notiz"
                  name="note"
                  required={false}
                  defaultValue={
                    editingStay?.note || String(createDraft?.note || "")
                  }
                />
              </>
            )}
            <div className="form-actions">
              <button>
                {counterRequest
                  ? "Gegenvorschlag senden"
                  : editingStay && getSessionUser()?.role !== "ADMIN"
                    ? "Änderung vorschlagen"
                    : !editingStay &&
                        open === "stay" &&
                        getSessionUser()?.role !== "ADMIN"
                      ? "Vorschlag senden"
                      : "Speichern"}
              </button>
              {open === "stay" && editingStay && !counterRequest && (
                <button
                  type="button"
                  className="delete-button"
                  onClick={removeStay}
                >
                  {getSessionUser()?.role === "ADMIN"
                    ? "Löschen"
                    : "Löschung vorschlagen"}
                </button>
              )}
              {open === "event" &&
                editingEvent &&
                (getSessionUser()?.role === "ADMIN" ||
                  editingEvent.created_by_id === getSessionUser()?.id) && (
                  <button
                    type="button"
                    className="delete-button"
                    onClick={() => setEventDeleteChoice(editingEvent)}
                  >
                    {editingEvent.recurrence_group
                      ? eventEditScope === "series"
                        ? "Serie löschen"
                        : eventEditScope === "future"
                          ? "Diesen und zukünftige löschen"
                          : "Diesen Termin löschen"
                      : "Termin löschen"}
                  </button>
                )}
            </div>
          </form>
        </div>
      )}
      {dayCreateChoice && (
        <div className="modal decision-modal">
          <div className="panel">
            <button
              type="button"
              className="close"
              onClick={() => setDayCreateChoice(null)}
            >
              ×
            </button>
            <h2>Termin hinzufügen</h2>
            <p>
              Neuen Termin am{" "}
              <strong>
                {dayCreateChoice.day.toLocaleDateString("de-DE")}
              </strong>{" "}
              eintragen.
            </p>
            <div className="decision-actions create-kind-actions">
              <button
                type="button"
                onClick={() => {
                  setSelectedDay(dayCreateChoice.day);
                  setDayCreateChoice(null);
                  setEditingEvent(null);
                  setEventType("GENERAL");
                  setEventRepeatKind("once");
                  setError("");
                  setOpen("event");
                }}
              >
                <CalendarDays size={18} /> Termin anlegen
              </button>
              {dayCreateChoice.holidays.length > 0 && (
                <button
                  type="button"
                  className="secondary"
                  onClick={() => {
                    const holiday = dayCreateChoice.holidays[0];
                    const child = children.find(
                      (item) => item.school_state_code === holiday.state,
                    );
                    const startsAt = new Date(`${holiday.starts_on}T00:00:00`);
                    const endsAt = new Date(`${holiday.ends_on}T00:00:00`);
                    endsAt.setDate(endsAt.getDate() + 1);
                    setCreateDraft({
                      child_id: child?.id,
                      responsible_user_id:
                        child?.default_responsible_user_id ||
                        getSessionUser()?.id,
                      starts_at: startsAt.toISOString(),
                      ends_at: endsAt.toISOString(),
                      note: `Ferien: ${holiday.name}`,
                    });
                    setSelectedDay(startsAt);
                    setDayCreateChoice(null);
                    setEditingStay(null);
                    setCounterRequest(null);
                    setRepeatKind("once");
                    setError("");
                    setOpen("stay");
                  }}
                >
                  <Palmtree size={18} /> Ferienabschnitt planen
                </button>
              )}
            </div>
          </div>
        </div>
      )}
      {eventDeleteChoice && (
        <div className="modal decision-modal">
          <div className="panel">
            <button
              type="button"
              className="close"
              onClick={() => setEventDeleteChoice(null)}
            >
              ×
            </button>
            <h2>
              {eventDeleteChoice.recurrence_group && eventEditScope === "series"
                ? "Terminserie löschen?"
                : eventDeleteChoice.recurrence_group && eventEditScope === "future"
                  ? "Zukünftige Termine löschen?"
                : "Termin löschen?"}
            </h2>
            <p>
              {eventDeleteChoice.recurrence_group && eventEditScope === "series"
                ? `Möchtest du die gesamte Serie „${eventDeleteChoice.title}“ mit allen Terminen wirklich löschen?`
                : eventDeleteChoice.recurrence_group && eventEditScope === "future"
                  ? `Möchtest du diesen und alle zukünftigen Termine von „${eventDeleteChoice.title}“ wirklich löschen?`
                : `Möchtest du den Termin „${eventDeleteChoice.title}“ wirklich löschen?`}
            </p>
            {error && <p className="error">{error}</p>}
            <div className="decision-actions">
              <button type="button" className="danger" onClick={deleteEvent}>
                {eventDeleteChoice.recurrence_group && eventEditScope === "series"
                  ? "Gesamte Serie löschen"
                  : eventDeleteChoice.recurrence_group && eventEditScope === "future"
                    ? "Zukünftige Termine löschen"
                  : "Termin löschen"}
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => setEventDeleteChoice(null)}
              >
                Abbrechen
              </button>
            </div>
          </div>
        </div>
      )}
      {adminChoice && (
        <div className="modal decision-modal">
          <div className="panel">
            <button
              type="button"
              className="close"
              onClick={() => setAdminChoice(null)}
            >
              ×
            </button>
            <h2>Änderung übernehmen?</h2>
            <p>
              Du kannst die Änderung als Administrator sofort übernehmen oder
              der ausgewählten Person zur Bestätigung senden.
            </p>
            {error && <p className="error">{error}</p>}
            <div className="decision-actions">
              <button type="button" onClick={() => applyAdminChange(false)}>
                Direkt übernehmen
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => applyAdminChange(true)}
              >
                Änderungsanfrage senden
              </button>
            </div>
          </div>
        </div>
      )}
      {adminCreateChoice && (
        <div className="modal decision-modal">
          <div className="panel">
            <button
              type="button"
              className="close"
              onClick={() => setAdminCreateChoice(null)}
            >
              ×
            </button>
            <h2>Betreuungszeit anlegen?</h2>
            <p>
              Du kannst die Betreuungszeit beziehungsweise die Serie sofort anlegen
              oder der aktuell zuständigen Person zur Bestätigung senden.
            </p>
            {error && <p className="error">{error}</p>}
            {createConflicts.map((stay) => (
              <div className="conflict-row" key={stay.id}>
                <span>
                  <b>{stay.responsible_display_name}</b>
                  <small>
                    {new Date(stay.starts_at).toLocaleString("de-DE")} –{" "}
                    {new Date(stay.ends_at).toLocaleString("de-DE")}
                  </small>
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setAdminCreateChoice(null);
                    setCreateConflicts([]);
                    setEditingStay(stay);
                    setSelectedDay(new Date(stay.starts_at));
                    setEditScope("occurrence");
                    setError("");
                    setOpen("stay");
                  }}
                >
                  Konflikt öffnen
                </button>
              </div>
            ))}
            <div className="decision-actions">
              <button type="button" onClick={() => applyAdminCreate(false)}>
                Direkt anlegen
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => applyAdminCreate(true)}
              >
                Zur Bestätigung senden
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  setCreateDraft(adminCreateChoice);
                  setAdminCreateChoice(null);
                  setError("");
                  setOpen("stay");
                }}
              >
                Angaben ändern
              </button>
            </div>
          </div>
        </div>
      )}
      {adminDeleteChoice && (
        <div className="modal decision-modal">
          <div className="panel">
            <button
              type="button"
              className="close"
              onClick={() => setAdminDeleteChoice(null)}
            >
              ×
            </button>
            <h2>Betreuungszeit löschen?</h2>
            <p>
              Du kannst als Administrator sofort löschen oder der aktuell
              zuständigen Person eine Löschanfrage senden.
            </p>
            {error && <p className="error">{error}</p>}
            <div className="decision-actions">
              <button type="button" onClick={() => applyAdminDeletion(false)}>
                Sofort löschen
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => applyAdminDeletion(true)}
              >
                Löschung vorschlagen
              </button>
            </div>
          </div>
        </div>
      )}
      {deleteProposalChoice && (
        <div className="modal decision-modal">
          <div className="panel">
            <button
              type="button"
              className="close"
              onClick={() => setDeleteProposalChoice(null)}
            >
              ×
            </button>
            <h2>Löschung vorschlagen?</h2>
            <p>
              Möchtest du {deleteProposalChoice.label} wirklich zur Löschung
              vorschlagen? Die zuständige andere Person muss anschließend
              zustimmen.
            </p>
            <p className="hint">
              Das Enddatum ist nicht eingeschlossen: „bis 04.10., 00:00“
              betrifft den 04.10. nicht.
            </p>
            {error && <p className="error">{error}</p>}
            <div className="decision-actions">
              <button type="button" onClick={sendDeletionProposal}>
                Löschung vorschlagen
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => setDeleteProposalChoice(null)}
              >
                Abbrechen
              </button>
            </div>
          </div>
        </div>
      )}
      {groupReview && (
        <div className="modal group-review-modal">
          <div className="panel">
            <button type="button" className="close" onClick={() => setGroupReview(null)}>×</button>
            <h2>Gruppenplanung prüfen</h2>
            <p><b>{groupReview.proposed_data.title || "Gemeinsame Planung"}</b> von {groupReview.requested_by_name}</p>
            {error && <p className="error">{error}</p>}
            <div className="groupreviewlist">
              {groupReviewItems.map((item, index) => {
                const canEdit = getSessionUser()?.id === groupReview.affected_user_id;
                const startDate = new Date(item.starts_at);
                const rawEndDate = new Date(item.ends_at);
                const endAtDayBoundary = rawEndDate.getHours() === 0 && rawEndDate.getMinutes() === 0;
                const endDate = endAtDayBoundary ? new Date(rawEndDate.getTime() - 1) : rawEndDate;
                const dateValue = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
                const timeValue = (date: Date) => `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
                const startTime = startDate.getHours() === 0 && startDate.getMinutes() === 0 ? "" : timeValue(startDate);
                const endTime = endAtDayBoundary ? "" : timeValue(rawEndDate);
                const toIso = (value: string, time: string, followingDay = false) => {
                  const date = new Date(`${value}T${time || "00:00"}:00`);
                  if (followingDay && !time) date.setDate(date.getDate() + 1);
                  return date.toISOString();
                };
                return (
                  <article key={item.stay_id || index}>
                    <header><span className="tag">Abschnitt {index + 1}</span><strong>{item.name}</strong></header>
                    <div className="groupreviewfields">
                      <label>Kind<select disabled value={item.child_id}>{children.map((child) => <option key={child.id} value={child.id}>{child.display_name}</option>)}</select></label>
                      <label>Bei Person<select disabled={!canEdit} value={item.responsible_user_id} onChange={(e) => updateGroupReview(index, { responsible_user_id: Number(e.target.value) })}>{people.map((person) => <option key={person.id} value={person.id}>{person.display_name}</option>)}</select></label>
                      <label>Von<input disabled={!canEdit} type="date" value={dateValue(startDate)} onChange={(e) => updateGroupReview(index, { starts_at: toIso(e.target.value, startTime) })} /></label>
                      <label>Von Uhr<input disabled={!canEdit} type="time" value={startTime} onChange={(e) => updateGroupReview(index, { starts_at: toIso(dateValue(startDate), e.target.value) })} placeholder="ganztägig" /></label>
                      <label>Bis<input disabled={!canEdit} type="date" value={dateValue(endDate)} onChange={(e) => updateGroupReview(index, { ends_at: toIso(e.target.value, endTime, true) })} /></label>
                      <label>Bis Uhr<input disabled={!canEdit} type="time" value={endTime} onChange={(e) => updateGroupReview(index, { ends_at: toIso(dateValue(endDate), e.target.value, true) })} placeholder="ganztägig" /></label>
                    </div>
                    <label>Kommentar zu diesem Abschnitt<textarea disabled={!canEdit} value={item.comment || ""} onChange={(e) => updateGroupReview(index, { comment: e.target.value })} placeholder="Optional bei Bestätigung oder Gegenvorschlag; bei Ablehnung ist eine Begründung erforderlich." maxLength={1000} /></label>
                  </article>
                );
              })}
            </div>
            {getSessionUser()?.id === groupReview.affected_user_id ? (
              <div className="decision-actions groupreviewactions">
                <button disabled={groupReviewBusy} onClick={() => decideGroup("APPROVE")}>{groupReviewBusy ? "Wird verarbeitet …" : "Gesamte Planung bestätigen"}</button>
                <button disabled={groupReviewBusy} className="secondary" onClick={() => decideGroup("COUNTER")}>Geänderten Vorschlag senden</button>
                <button disabled={groupReviewBusy} className="secondary danger" onClick={() => decideGroup("REJECT")}>Planung ablehnen</button>
              </div>
            ) : <p className="hint">Diese Fassung wartet auf die Entscheidung von {groupReview.affected_user_name}.</p>}
          </div>
        </div>
      )}
      {rejectingRequest && (
        <div className="modal decision-modal">
          <form
            className="panel"
            onSubmit={(event) => {
              event.preventDefault();
              const comment = String(
                new FormData(event.currentTarget).get("comment") || "",
              ).trim();
              if (comment) decide(rejectingRequest, "REJECT", comment);
            }}
          >
            <button
              type="button"
              className="close"
              onClick={() => setRejectingRequest(null)}
            >
              ×
            </button>
            <h2>Vorschlag ablehnen?</h2>
            <p>
              Die Begründung wird {rejectingRequest.requested_by_name} als
              Benachrichtigung übermittelt.
            </p>
            {error && <p className="error">{error}</p>}
            <label>
              Begründung
              <textarea name="comment" required maxLength={1000} autoFocus />
            </label>
            <div className="decision-actions">
              <button type="submit" className="danger">
                Ablehnung senden
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => setRejectingRequest(null)}
              >
                Abbrechen
              </button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}

function PeopleScreen({
  people,
  reload,
}: {
  people: User[];
  reload: () => void;
}) {
  const isAdmin = getSessionUser()?.role === "ADMIN";
  const [open, setOpen] = useState<"invite" | "edit" | null>(null),
    [selected, setSelected] = useState<PersonAccess | null>(null),
    [invite, setInvite] = useState(""),
    [inviteEmail, setInviteEmail] = useState<string | null>(null),
    [copied, setCopied] = useState(false),
    [notice, setNotice] = useState<{ title: string; message: string } | null>(null),
    [impersonateChoice, setImpersonateChoice] = useState<User | null>(null),
    [deleteChoice, setDeleteChoice] = useState<User | null>(null),
    [deletingPerson, setDeletingPerson] = useState(false),
    [error, setError] = useState(""),
    [children, setChildren] = useState<Child[]>([]),
    [access, setAccess] = useState<PersonAccess[]>([]);
  function load() {
    api<Child[]>("/children").then(setChildren);
    if (isAdmin) {
      api<PersonAccess[]>("/people/access")
        .then(setAccess)
        .catch(() => {});
    }
  }
  useEffect(load, [people.length]);
  function permissions(f: FormData, role: string) {
    return Object.fromEntries(
      f
        .getAll("children")
        .map((id) => [String(id), role === "EDITOR" ? "EDIT" : "VIEW"]),
    );
  }
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget),
      role = String(f.get("role"));
    try {
      if (open === "edit" && selected) {
        await api(`/people/${selected.user.id}/access`, {
          method: "PUT",
          body: JSON.stringify({
            username: String(f.get("username")),
            display_name: String(f.get("display_name")),
            first_name: f.get("first_name") || null,
            last_name: f.get("last_name") || null,
            email: f.get("email") || null,
            role,
            color: String(f.get("color")),
            birth_date: f.get("birth_date") || null,
            allowed_event_types: f.getAll("allowed_event_types"),
            child_permissions: permissions(f, role),
          }),
        });
        setOpen(null);
        load();
        reload();
      } else {
        const r = await api<{ invite_url: string; email: string | null }>("/invitations", {
          method: "POST",
          body: JSON.stringify({
            display_name: f.get("display_name"),
            email: f.get("email") || null,
            send_email: f.get("send_email") === "on",
            role,
            child_permissions: permissions(f, role),
          }),
        });
        setInvite(r.invite_url);
        setInviteEmail(r.email);
        load();
        reload();
      }
    } catch (x) {
      setError((x as Error).message);
    }
  }
  async function copy() {
    await navigator.clipboard.writeText(invite);
    setCopied(true);
  }
  function edit(p: User) {
    setSelected(
      access.find((a) => a.user.id === p.id) || {
        user: p,
        child_permissions: {},
      },
    );
    setError("");
    setInvite("");
    setInviteEmail(null);
    setCopied(false);
    if (p.is_pending) {
      api<{ invite_url: string; email: string | null }>(`/people/${p.id}/invitation`).then((result) => { setInvite(result.invite_url); setInviteEmail(result.email); }).catch(() => {});
    }
    setOpen("edit");
  }
  return (
    <>
      <header className="pagehead">
        <div>
          <span className="eyebrow">Familie</span>
          <h1>Personen</h1>
          <p>
            {isAdmin
              ? "Zugriff und freigegebene Kinder verwalten."
              : "Personen in deiner Familienplanung."}
          </p>
        </div>
        {isAdmin && (
          <button
            onClick={() => {
              setInvite("");
              setInviteEmail(null);
              setSelected(null);
              setCopied(false);
              setError("");
              setOpen("invite");
            }}
          >
            <UserPlus size={18} /> Person einladen
          </button>
        )}
      </header>
      <div className="cards">
        {people.map((p) => (
          <button
            className="childcard"
            key={p.id}
            onClick={() => isAdmin && edit(p)}
            disabled={!isAdmin}
          >
            <div
              className="avatar"
              style={{
                backgroundColor: `color-mix(in srgb, ${p.color} 18%, white)`,
                color: p.color,
              }}
            >
              {p.display_name[0]}
            </div>
            <h2>{p.display_name}</h2>
            <p>{p.is_pending ? "Noch nicht registriert" : p.email}</p>
            <span className="tag">
              {p.is_pending
                ? "Einladung ausstehend"
                : p.role === "ADMIN"
                ? "Administrator"
                : p.role === "EDITOR"
                  ? "Darf planen"
                  : "Nur lesen"}
            </span>
            <p>
              {p.role === "ADMIN"
                ? "Alle Kinder"
                : `${Object.keys(access.find((a) => a.user.id === p.id)?.child_permissions || {}).length} Kinder freigegeben`}
            </p>
          </button>
        ))}
      </div>
      {isAdmin && open && (
        <div className="modal">
          <form className="panel personform" onSubmit={submit}>
            <button
              type="button"
              className="close"
              onClick={() => setOpen(null)}
            >
              ×
            </button>
            <h2>{open === "edit" ? "Person bearbeiten" : "Person einladen"}</h2>
            {error && <p className="error">{error}</p>}
            {invite && open === "invite" ? (
              <>
                <p>Einladungslink – bitte sicher an die Person senden:</p>
                <div className="copyrow">
                  <input
                    readOnly
                    value={invite}
                    onFocus={(e) => e.currentTarget.select()}
                  />
                  <button
                    type="button"
                    onClick={copy}
                    title="In die Zwischenablage kopieren"
                  >
                    <Copy />
                    {copied ? "Kopiert" : "Kopieren"}
                  </button>
                </div>
              </>
            ) : (
              <>
                <>
                  {open === "invite" && (
                    <>
                      <Field label="Anzeigename" name="display_name" />
                      <Field label="E-Mail-Adresse (optional)" name="email" type="email" required={false} />
                      <label className="check"><input type="checkbox" name="send_email" /><span>Einladungslink sofort per E-Mail senden</span></label>
                    </>
                  )}
                </>
                <label>
                  Zugriff
                  <select
                    name="role"
                    defaultValue={selected?.user.role || "EDITOR"}
                  >
                    <option value="EDITOR">
                      Darf planen und Vorschläge machen
                    </option>
                    <option value="VIEWER">Darf nur lesen</option>
                    <option value="ADMIN">
                      Administrator – Zugriff auf alles
                    </option>
                  </select>
                </label>
                {open === "edit" && (
                  <>
                    {selected?.user.is_pending && invite && (
                      <div className="pending-invitation">
                        <strong>Einladung noch nicht angenommen</strong>
                        <div className="copyrow"><input readOnly value={invite} onFocus={(e) => e.currentTarget.select()} /><button type="button" onClick={copy}><Copy />{copied ? "Kopiert" : "Link kopieren"}</button></div>
                        <button type="button" className="secondary" onClick={async () => {
                          const renewed = await api<{ invite_url: string; email: string | null }>(`/people/${selected.user.id}/invitation/renew`, { method: "POST" });
                          setInvite(renewed.invite_url); setInviteEmail(renewed.email); setCopied(false);
                        }}>Neuen Einladungslink erzeugen</button>
                        {inviteEmail && <button type="button" onClick={async () => {
                          await api(`/people/${selected.user.id}/invitation/send`, { method: "POST" });
                          setNotice({ title: "Einladung wird versendet", message: `Die Einladung an ${inviteEmail} wurde in die Versandwarteschlange gelegt.` });
                        }}>Einladung jetzt per E-Mail senden</button>}
                      </div>
                    )}
                    <Field
                      label="Anzeigename"
                      name="display_name"
                      defaultValue={selected?.user.display_name || ""}
                    />
                    <div className="grid2">
                      <Field
                        label="Vorname"
                        name="first_name"
                        required={false}
                        defaultValue={selected?.user.first_name || ""}
                      />
                      <Field
                        label="Nachname"
                        name="last_name"
                        required={false}
                        defaultValue={selected?.user.last_name || ""}
                      />
                    </div>
                    {selected?.user.is_pending ? (
                      <>
                        <input type="hidden" name="username" value={selected.user.username} />
                        <Field key={`pending-email-${inviteEmail || "empty"}`} label="E-Mail-Adresse (optional)" name="email" type="email" required={false} defaultValue={inviteEmail || ""} />
                        <p className="hint">Den Benutzernamen und das Passwort legt die Person beim Annehmen der Einladung fest. Die E-Mail-Adresse kann vorher geändert oder ergänzt werden.</p>
                      </>
                    ) : (
                      <>
                        <Field label="Benutzername" name="username" defaultValue={selected?.user.username || ""} />
                        <Field label="E-Mail-Adresse" name="email" type="email" defaultValue={selected?.user.email || ""} />
                      </>
                    )}
                    <Field
                      label="Geburtsdatum (optional)"
                      name="birth_date"
                      type="date"
                      required={false}
                      defaultValue={selected?.user.birth_date || ""}
                    />
                    <label>
                      Kalenderfarbe
                      <div className="personcolor">
                        <input
                          type="color"
                          name="color"
                          defaultValue={selected?.user.color || "#3BA4E5"}
                        />
                        <span>Farbe für Betreuungszeiten dieser Person</span>
                      </div>
                    </label>
                  </>
                )}
                <fieldset className="childaccess">
                  <legend>Freigegebene Kinder</legend>
                  {children.map((c) => (
                    <label className="check" key={c.id}>
                      <input
                        type="checkbox"
                        name="children"
                        value={c.id}
                        defaultChecked={
                          selected?.user.role === "ADMIN" ||
                          !!selected?.child_permissions[String(c.id)]
                        }
                      />
                      <span>{c.display_name}</span>
                    </label>
                  ))}
                  {!children.length && (
                    <p className="hint">Noch keine Kinder vorhanden.</p>
                  )}
                </fieldset>
                {open === "edit" && (
                  <fieldset className="childaccess">
                    <legend>Freigeschaltete Terminarten</legend>
                    {sortedEventTypes((Object.keys(eventTypeLabels) as EventType[]).filter((type) => type !== "PRIVATE")).map((type) => (
                      <label className="check" key={type}>
                        <input
                          type="checkbox"
                          name="allowed_event_types"
                          value={type}
                          defaultChecked={(selected?.user.allowed_event_types || ["STAY", "BIRTHDAY", "GENERAL", "SCHOOL"]).includes(type)}
                        />
                        <span>{eventTypeLabels[type]}</span>
                      </label>
                    ))}
                  </fieldset>
                )}
                <div className="personform-actions">
                  <button>
                    {open === "edit"
                      ? "Änderungen speichern"
                      : "Einladung erstellen"}
                  </button>
                  {open === "edit" && selected && !selected.user.is_pending && selected.user.role !== "ADMIN" && (
                    <button type="button" className="secondary" onClick={() => setImpersonateChoice(selected.user)}>Als diese Person anmelden</button>
                  )}
                  {open === "edit" && selected && selected.user.id !== getSessionUser()?.id && (
                    <button type="button" className="danger" onClick={() => { setDeleteChoice(selected.user); setOpen(null); setError(""); }}>Person löschen</button>
                  )}
                </div>
              </>
            )}
          </form>
        </div>
      )}
      {notice && <div className="modal confirmmodal" role="dialog" aria-modal="true"><section className="panel"><button type="button" className="close" onClick={() => setNotice(null)} aria-label="Schließen">×</button><h2>{notice.title}</h2><p>{notice.message}</p><div className="modalactions"><button type="button" onClick={() => setNotice(null)}>Verstanden</button></div></section></div>}
      {impersonateChoice && <div className="modal confirmmodal" role="dialog" aria-modal="true"><section className="panel"><button type="button" className="close" onClick={() => setImpersonateChoice(null)} aria-label="Schließen">×</button><h2>Ansicht übernehmen?</h2><p>FamilienPlan wird als {impersonateChoice.display_name} geöffnet. Du kannst anschließend wieder zu deinem Administratorkonto zurückkehren.</p><div className="modalactions"><button type="button" onClick={async () => { await api(`/people/${impersonateChoice.id}/impersonate`, { method: "POST" }); location.reload(); }}>Als {impersonateChoice.display_name} öffnen</button><button type="button" className="secondary" onClick={() => setImpersonateChoice(null)}>Abbrechen</button></div></section></div>}
      {deleteChoice && <div className="modal confirmmodal" role="dialog" aria-modal="true"><section className="panel"><button type="button" className="close" onClick={() => { setDeleteChoice(null); setError(""); }} aria-label="Schließen">×</button><h2>Person löschen?</h2><p><strong>{deleteChoice.display_name}</strong> wird dauerhaft aus FamilienPlan entfernt. Bestehen bereits Planungs- oder Kalenderdaten dieser Person, verhindert FamilienPlan das Löschen.</p>{error && <p className="error">{error}</p>}<div className="modalactions"><button type="button" className="danger" disabled={deletingPerson} onClick={async () => { setDeletingPerson(true); setError(""); try { await api(`/people/${deleteChoice.id}`, { method: "DELETE" }); setDeleteChoice(null); reload(); } catch (x) { setError((x as Error).message); } finally { setDeletingPerson(false); } }}>{deletingPerson ? "Wird gelöscht …" : "Person endgültig löschen"}</button><button type="button" className="secondary" disabled={deletingPerson} onClick={() => { setDeleteChoice(null); setError(""); }}>Abbrechen</button></div></section></div>}
    </>
  );
}

function BirthdaysScreen() {
  const [items, setItems] = useState<Birthday[]>([]),
    [people, setPeople] = useState<User[]>([]),
    [editing, setEditing] = useState<Birthday | null | undefined>(undefined),
    [deleting, setDeleting] = useState<Birthday | null>(null),
    [error, setError] = useState("");
  const user = getSessionUser();
  function load() {
    api<Birthday[]>("/birthdays").then(setItems).catch((x) => setError((x as Error).message));
    api<User[]>("/people").then(setPeople).catch(() => {});
  }
  useEffect(() => { void load(); }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget),
      payload = {
        first_name: String(form.get("first_name")),
        last_name: String(form.get("last_name")),
        display_name: String(form.get("display_name")),
        birth_date: String(form.get("birth_date")),
        is_private: false,
        visible_to_user_ids: form.getAll("visible_to_user_ids").map(Number),
      };
    setError("");
    try {
      await api(editing ? `/birthdays/${editing.id}` : "/birthdays", {
        method: editing ? "PUT" : "POST",
        body: JSON.stringify(payload),
      });
      setEditing(undefined);
      load();
    } catch (x) {
      setError((x as Error).message);
    }
  }
  async function remove() {
    if (!deleting) return;
    try {
      await api(`/birthdays/${deleting.id}`, { method: "DELETE" });
      setDeleting(null);
      setEditing(undefined);
      load();
    } catch (x) {
      setError((x as Error).message);
    }
  }
  return (
    <>
      <header className="pagehead">
        <div>
          <span className="eyebrow">Kalender</span>
          <h1>Geburtstage</h1>
          <p>Geburtstage von Familie, Freunden und weiteren Personen verwalten.</p>
        </div>
        <button onClick={() => { setError(""); setEditing(null); }}>
          <Plus size={18} /> Geburtstag anlegen
        </button>
      </header>
      {error && <p className="error">{error}</p>}
      <div className="cards birthdaycards">
        {items.map((birthday) => {
          const canEdit = user?.role === "ADMIN" || birthday.created_by_id === user?.id;
          return (
            <button
              className="childcard"
              key={birthday.id}
              disabled={!canEdit}
              onClick={() => canEdit && setEditing(birthday)}
            >
              <div className="avatar"><Cake size={18} /></div>
              <h2>{birthday.display_name}</h2>
              <p>{birthday.first_name} {birthday.last_name}</p>
              <p>{new Date(`${birthday.birth_date}T12:00:00`).toLocaleDateString("de-DE")}</p>
              <span className="tag">Termin · Geburtstag</span>
              <span className="tag">{birthday.visible_to_user_ids ? `Für ${birthday.visible_to_user_ids.length} Person(en)` : "Für alle sichtbar"}</span>
            </button>
          );
        })}
      </div>
      {editing !== undefined && (
        <div className="modal">
          <form className="panel birthdayform" onSubmit={submit}>
            <button type="button" className="close" onClick={() => setEditing(undefined)}>×</button>
            <h2>{editing ? "Geburtstag bearbeiten" : "Geburtstag anlegen"}</h2>
            {error && <p className="error">{error}</p>}
            <div className="grid2">
              <Field label="Vorname" name="first_name" defaultValue={editing?.first_name || ""} />
              <Field label="Nachname" name="last_name" defaultValue={editing?.last_name || ""} />
            </div>
            <Field label="Anzeigename" name="display_name" defaultValue={editing?.display_name || ""} />
            <Field label="Geburtsdatum" name="birth_date" type="date" defaultValue={editing?.birth_date || ""} />
            <AudiencePicker
              key={`birthday-audience-${editing?.id || "new"}`}
              people={people}
              initialValues={editing?.visible_to_user_ids}
            />
            <div className="modalactions">
              <button>{editing ? "Speichern" : "Anlegen"}</button>
              {editing && <button type="button" className="danger secondary" onClick={() => setDeleting(editing)}>Löschen</button>}
            </div>
          </form>
        </div>
      )}
      {deleting && (
        <div className="modal confirmmodal">
          <section className="panel">
            <h2>Geburtstag löschen?</h2>
            <p>„{deleting.display_name}“ wird dauerhaft aus dem Kalender entfernt.</p>
            <div className="modalactions">
              <button className="danger" onClick={remove}>Löschen</button>
              <button className="secondary" onClick={() => setDeleting(null)}>Abbrechen</button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}

function WasteCollectionScreen({ people, children }: { people: User[]; children: Child[] }) {
  const [items, setItems] = useState<CalendarEvent[]>([]),
    [editing, setEditing] = useState<CalendarEvent | null | undefined>(undefined),
    [deleting, setDeleting] = useState<CalendarEvent | null>(null),
    [repeat, setRepeat] = useState<"once" | "weekly1" | "weekly2" | "weeklyCustom" | "monthlySame" | "monthlyDay" | "monthlyCustom">("once"),
    [error, setError] = useState(""),
    [calendarSettings, setCalendarSettings] = useState<WasteCalendarSetting | null>(null),
    [calendarOpen, setCalendarOpen] = useState(false),
    [syncing, setSyncing] = useState(false),
    [syncMessage, setSyncMessage] = useState("");
  const canEdit = true;
  const load = () => api<CalendarEvent[]>("/waste-appointments").then(setItems).catch((x) => setError((x as Error).message));
  useEffect(() => {
    void load();
    api<WasteCalendarSetting>("/waste-calendar/settings").then(setCalendarSettings).catch(() => {});
  }, []);
  async function saveCalendar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!calendarSettings) return;
    const form = new FormData(event.currentTarget);
    try {
      const saved = await api<WasteCalendarSetting>("/waste-calendar/settings", { method: "PUT", body: JSON.stringify({
        ...calendarSettings,
        enabled: form.get("enabled") === "on",
        provider: String(form.get("provider")) as "AWIDO" | "ICAL",
        customer: String(form.get("customer") || "awld"), city: String(form.get("city") || ""),
        street: String(form.get("street") || ""), calendar_url: String(form.get("calendar_url") || ""),
        color: String(form.get("color") || "#5C8B58"),
        type_colors: Object.fromEntries(Object.keys(wasteTypeLabels).map((type) => [type, String(form.get(`type_color_${type}`) || calendarSettings.type_colors[type])])),
        visible_to_user_ids: form.getAll("visible_to_user_ids").map(Number),
      }) });
      setCalendarSettings(saved); setCalendarOpen(false);
      if (saved.enabled) {
        setSyncing(true);
        const result = await api<{ imported: number; message: string }>("/waste-calendar/sync", { method: "POST" });
        setSyncMessage(`Einstellungen gespeichert. ${result.message}`);
        setCalendarSettings(await api<WasteCalendarSetting>("/waste-calendar/settings"));
        load();
        setSyncing(false);
      } else {
        setSyncMessage("Einstellungen gespeichert.");
      }
    } catch (x) { setError((x as Error).message); setSyncing(false); }
  }
  async function syncCalendar() {
    setSyncing(true); setError(""); setSyncMessage("");
    try {
      const result = await api<{ imported: number; message: string }>("/waste-calendar/sync", { method: "POST" });
      setSyncMessage(result.message); load();
      setCalendarSettings(await api<WasteCalendarSetting>("/waste-calendar/settings"));
    } catch (x) { setError((x as Error).message); }
    finally { setSyncing(false); }
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const monthly = repeat.startsWith("monthly"),
        frequency = repeat === "once" ? null : monthly ? "MONTHLY" : "WEEKLY",
        interval = repeat === "once" ? null : repeat === "weekly2" ? 2 : ["weeklyCustom", "monthlyCustom"].includes(repeat) ? Number(form.get("repeat_custom")) || null : 1;
      await api(editing ? `/calendar/${editing.id}?scope=${editing.recurrence_group ? "series" : "occurrence"}` : "/calendar", {
        method: editing ? "PUT" : "POST",
        body: JSON.stringify({
          title: String(form.get("title")), description: form.get("description") || null,
          starts_at: new Date(String(form.get("starts_at"))).toISOString(), ends_at: new Date(String(form.get("ends_at"))).toISOString(),
          all_day: false, category: "FAMILY", event_type: "WASTE", custom_type_label: null,
          child_id: Number(form.get("child_id")) || null, color: String(form.get("color")), is_private: false,
          visible_to_user_ids: form.getAll("visible_to_user_ids").map(Number), recurrence_frequency: frequency,
          recurrence_interval: interval,
          recurrence_day_of_month: repeat === "monthlyDay" ? Number(form.get("recurrence_day")) || null : null,
          recurrence_until: frequency && form.get("recurrence_until") ? new Date(String(form.get("recurrence_until")) + "T23:59").toISOString() : null,
        }),
      });
      setEditing(undefined); load();
    } catch (x) { setError((x as Error).message); }
  }
  async function remove(item: CalendarEvent) {
    try { await api(`/calendar/${item.id}?scope=${item.recurrence_group ? "series" : "occurrence"}`, { method: "DELETE" }); setEditing(undefined); load(); }
    catch (x) { setError((x as Error).message); }
  }
  const start = editing ? new Date(editing.starts_at) : new Date(), end = editing ? new Date(editing.ends_at) : new Date(start.getTime() + 3600000);
  return <>
    <header className="pagehead"><div><span className="eyebrow">Kalender</span><h1>Abfallkalender</h1><p>Automatische Abfuhrpläne einrichten und eigene Abholtermine verwalten.</p></div>{canEdit && <button onClick={() => { setError(""); setRepeat("once"); setEditing(null); }}><Plus size={18}/> Abholtermin</button>}</header>
    {error && <p className="error">{error}</p>}
    {syncMessage && <p className="success">{syncMessage}</p>}
    {calendarSettings && <section className="themebox waste-import-card">
      <div><h2>Automatischer Abfallkalender</h2><p className="muted">{calendarSettings.enabled ? `${calendarSettings.provider === "AWIDO" ? `${calendarSettings.city} · ${calendarSettings.street}` : "iCal/WebCal"} · tägliche Synchronisierung` : "Noch nicht aktiviert"}</p>
      {calendarSettings.last_sync_at && <small>Zuletzt synchronisiert: {new Date(calendarSettings.last_sync_at).toLocaleString("de-DE")}{calendarSettings.last_result?.events !== undefined ? ` · ${calendarSettings.last_result.events} Termine` : ""}</small>}
      {calendarSettings.last_error && <p className="error">{calendarSettings.last_error}</p>}</div>
      <div className="waste-import-actions"><button type="button" className="secondary" onClick={() => setCalendarOpen(true)}>Einrichten</button>{calendarSettings.enabled && <button type="button" onClick={syncCalendar} disabled={syncing}>{syncing ? "Synchronisiere …" : "Jetzt synchronisieren"}</button>}</div>
    </section>}
    <h2 className="sectiontitle">Manuell angelegte Abholtermine</h2>
    {!items.length && <p className="hint">Keine manuellen Abholtermine vorhanden. Automatisch importierte Termine findest du im normalen Kalender.</p>}
    <div className="cards">{items.map((item) => <button className="childcard" key={item.id} onClick={() => { if (!canEdit) return; setRepeat(item.recurrence_frequency === "MONTHLY" ? item.recurrence_interval === 1 ? "monthlySame" : "monthlyCustom" : item.recurrence_frequency === "WEEKLY" ? item.recurrence_interval === 2 ? "weekly2" : item.recurrence_interval === 1 ? "weekly1" : "weeklyCustom" : "once"); setEditing(item); }} disabled={!canEdit}><div className="avatar"><Trash2 size={18}/></div><h2>{item.title}</h2><p>{new Date(item.starts_at).toLocaleString("de-DE")}</p><span className="tag">Termin · Abfallkalender{item.recurrence_group ? " · Serie" : ""}</span></button>)}</div>
    {editing !== undefined && <div className="modal"><form className="panel" onSubmit={submit}><button type="button" className="close" onClick={() => setEditing(undefined)}>×</button><h2>{editing ? "Abholtermin bearbeiten" : "Abholtermin anlegen"}</h2>
      <Field label="Abfallart / Titel" name="title" defaultValue={editing?.title || ""}/>
      <label>Kind (optional)<select name="child_id" defaultValue={editing?.child_id || (children.length === 1 ? children[0].id : "")}><option value="">Ganze Familie</option>{children.map((child) => <option key={child.id} value={child.id}>{child.display_name}</option>)}</select></label>
      <div className="grid2"><Field label="Abholung" name="starts_at" type="datetime-local" defaultValue={localDateTime(start)}/><Field label="Ende" name="ends_at" type="datetime-local" defaultValue={localDateTime(end)}/></div>
      <label>Wiederholung<select value={repeat} onChange={(event) => setRepeat(event.target.value as typeof repeat)}><option value="once">Einmalig</option><option value="weekly1">Jede Woche</option><option value="weekly2">Alle zwei Wochen</option><option value="weeklyCustom">Alle X Wochen</option><option value="monthlySame">Jeden Monat am gleichen Tag</option><option value="monthlyDay">Jeden Monat am X. Tag</option><option value="monthlyCustom">Alle X Monate</option></select></label>
      {(repeat === "weeklyCustom" || repeat === "monthlyCustom") && <Field label={repeat === "monthlyCustom" ? "Abstand in Monaten" : "Abstand in Wochen"} name="repeat_custom" type="number" defaultValue={editing?.recurrence_interval?.toString() || ""}/>}
      {repeat === "monthlyDay" && <Field label="Tag im Monat (1–31)" name="recurrence_day" type="number" defaultValue={new Date(editing?.starts_at || Date.now()).getDate().toString()}/>}
      {repeat !== "once" && <Field label="Wiederholen bis (leer = ohne Ende)" name="recurrence_until" type="date" required={false} defaultValue={editing?.recurrence_until?.slice(0, 10) || ""}/>}
      <Field label="Notiz" name="description" required={false} defaultValue={editing?.description || ""}/><label>Farbe<input name="color" type="color" defaultValue={editing?.color || "#5C8B58"}/></label>
      <AudiencePicker key={`waste-audience-${editing?.id || "new"}`} people={people} initialValues={editing?.visible_to_user_ids}/>
      <div className="modalactions"><button>{editing ? "Speichern" : "Anlegen"}</button>{editing && <button type="button" className="danger secondary" onClick={() => setDeleting(editing)}>Löschen</button>}</div>
    </form></div>}
    {deleting && <div className="modal confirmmodal"><section className="panel"><button type="button" className="close" onClick={() => setDeleting(null)}>×</button><h2>{deleting.recurrence_group ? "Abholserie löschen?" : "Abholtermin löschen?"}</h2><p>{deleting.recurrence_group ? `Die gesamte Serie „${deleting.title}“ mit allen Abholterminen wird dauerhaft gelöscht.` : `Der Abholtermin „${deleting.title}“ wird dauerhaft gelöscht.`}</p><div className="modalactions"><button type="button" className="danger" onClick={async () => { await remove(deleting); setDeleting(null); }}>{deleting.recurrence_group ? "Gesamte Serie löschen" : "Termin löschen"}</button><button type="button" className="secondary" onClick={() => setDeleting(null)}>Abbrechen</button></div></section></div>}
    {calendarOpen && calendarSettings && <div className="modal"><form className="panel" onSubmit={saveCalendar}><button type="button" className="close" onClick={() => setCalendarOpen(false)}>×</button><h2>Abfallkalender einrichten</h2>
      <label className="check"><input type="checkbox" name="enabled" defaultChecked={calendarSettings.enabled}/><span>Automatische tägliche Synchronisierung aktivieren</span></label>
      <label>Anbieter<select name="provider" value={calendarSettings.provider} onChange={(e) => setCalendarSettings({...calendarSettings, provider: e.target.value as "AWIDO" | "ICAL"})}><option value="AWIDO">AWIDO</option><option value="ICAL">iCal-/WebCal-Adresse</option></select></label>
      {calendarSettings.provider === "AWIDO" ? <><Field label="AWIDO-Kennung" name="customer" defaultValue={calendarSettings.customer || "awld"}/><div className="grid2"><Field label="Gemeinde / Stadt" name="city" defaultValue={calendarSettings.city}/><Field label="Ortsteil / Straße" name="street" defaultValue={calendarSettings.street}/></div><p className="hint">Für Hohenahr-Ahrdt: Kennung <code>awld</code>, Gemeinde <code>Hohenahr</code>, Ortsteil <code>Ahrdt</code>.</p></> : <Field label="iCal-/WebCal-Adresse" name="calendar_url" type="url" defaultValue={calendarSettings.calendar_url}/>}
      <label>Grundfarbe des Abfallkalenders<div className="themepicker"><input type="color" name="color" value={calendarSettings.color || "#5C8B58"} onChange={(event) => setCalendarSettings({...calendarSettings, color: event.target.value})}/><code>{(calendarSettings.color || "#5C8B58").toUpperCase()}</code></div></label>
      <fieldset className="waste-type-colors"><legend>Farben der Abfallarten</legend>{Object.entries(wasteTypeLabels).map(([type, label]) => <label key={type}><span>{label}</span><div className="themepicker"><input type="color" name={`type_color_${type}`} value={calendarSettings.type_colors[type]} onChange={(event) => setCalendarSettings({...calendarSettings, type_colors: {...calendarSettings.type_colors, [type]: event.target.value}})}/><code>{calendarSettings.type_colors[type].toUpperCase()}</code></div></label>)}</fieldset>
      <fieldset className="childaccess"><legend>Sichtbar für</legend>{people.filter((person) => person.role !== "ADMIN").map((person) => <label className="check" key={person.id}><input type="checkbox" name="visible_to_user_ids" value={person.id} defaultChecked={calendarSettings.visible_to_user_ids.includes(person.id)}/><span>{person.display_name}</span></label>)}<p className="hint">Administratoren sehen die Termine immer.</p></fieldset>
      <button>Einstellungen speichern</button>
    </form></div>}
  </>;
}

function HolidaysScreen({
  children,
  onPlan,
  planningItems,
}: {
  children: Child[];
  onPlan: (holiday: HolidayPlanningDraft & { kind: PlanningItem["kind"] }) => void;
  planningItems: PlanningItem[];
}) {
  const year = new Date().getFullYear(),
    [state, setState] = useState("HE"),
    [childId, setChildId] = useState(""),
    [items, setItems] = useState<Array<Holiday & { year: number }>>([]),
    [publicItems, setPublicItems] = useState<Array<Holiday & { year: number }>>([]),
    [schoolItems, setSchoolItems] = useState<CalendarEvent[]>([]),
    [plannedStays, setPlannedStays] = useState<Stay[]>([]),
    [pendingPlanning, setPendingPlanning] = useState<ChangeRequest[]>([]),
    [error, setError] = useState("");
  function load() {
    setError("");
    const years = Array.from({ length: 5 }, (_, index) => year + index);
    Promise.all(
      years.map((itemYear) =>
        api<Holiday[]>(`/holidays?year=${itemYear}&state=${state}`).then(
          (holidays) =>
            holidays.map((holiday) => ({ ...holiday, year: itemYear })),
        ),
      ),
    )
      .then((values) => setItems(values.flat()))
      .catch((x) => setError((x as Error).message));
    Promise.all(
      years.map((itemYear) =>
        api<Holiday[]>(`/public-holidays?year=${itemYear}&state=${state}`).then(
          (holidays) =>
            holidays.map((holiday) => ({ ...holiday, year: itemYear })),
        ),
      ),
    )
      .then((values) => setPublicItems(values.flat()))
      .catch((x) => setError((x as Error).message));
    if (childId) {
      const from = new Date(year, 0, 1),
        to = new Date(year + 5, 0, 1);
      api<CalendarEvent[]>(
        `/calendar?from_at=${from.toISOString()}&to_at=${to.toISOString()}`,
      )
        .then((events) =>
          setSchoolItems(
            events.filter(
              (event) =>
                event.child_id === Number(childId) &&
                event.category === "SCHOOL" &&
                /brück|beweglich|unterrichtsfrei|schulfrei|ferien|feiertag/i.test(
                  `${event.title} ${event.description || ""}`,
                ),
            ),
          ),
        )
        .catch((x) => setError((x as Error).message));
      api<Stay[]>(
        `/children/${childId}/stays?from_at=${from.toISOString()}&to_at=${to.toISOString()}`,
      )
        .then(setPlannedStays)
        .catch((x) => setError((x as Error).message));
      api<ChangeRequest[]>("/change-requests")
        .then(setPendingPlanning)
        .catch((x) => setError((x as Error).message));
    } else {
      setSchoolItems([]);
      setPlannedStays([]);
      setPendingPlanning([]);
    }
  }
  useEffect(load, [state, childId]);
  function selectChild(value: string) {
    setChildId(value);
    const child = children.find((item) => item.id === Number(value));
    if (child?.school_state_code) setState(child.school_state_code);
  }
  useEffect(() => {
    if (children.length === 1 && !childId) {
      selectChild(String(children[0].id));
    }
  }, [children.length, childId]);
  type OverviewEntry = {
    key: string;
    year: number;
    name: string;
    startsOn: string;
    endsOn: string;
    kind: "FERIEN" | "FEIERTAG" | "SCHULE";
  };
  const holidayEntries = new Map<string, OverviewEntry>();
  items.forEach((item) => {
    const key = `ferien-${item.name}-${item.starts_on}-${item.ends_on}`;
    if (!holidayEntries.has(key))
      holidayEntries.set(key, {
        key,
        year: item.year,
        name: item.name,
        startsOn: item.starts_on,
        endsOn: item.ends_on,
        kind: "FERIEN",
      });
  });
  publicItems.forEach((item) => {
    const key = `feiertag-${item.name}-${item.starts_on}-${item.ends_on}`;
    if (!holidayEntries.has(key))
      holidayEntries.set(key, {
        key,
        year: item.year,
        name: item.name,
        startsOn: item.starts_on,
        endsOn: item.ends_on,
        kind: "FEIERTAG",
      });
  });
  schoolItems.forEach((item) => {
    const start = new Date(item.starts_at),
      end = new Date(item.ends_at),
      inclusiveEnd = item.all_day
        ? new Date(end.getTime() - 1)
        : end,
      startsOn = localDateTime(start).slice(0, 10),
      endsOn = localDateTime(inclusiveEnd).slice(0, 10),
      key = `schule-${item.id}`;
    holidayEntries.set(key, {
      key,
      year: start.getFullYear(),
      name: item.title,
      startsOn,
      endsOn,
      kind: "SCHULE",
    });
  });
  const entriesByYear = Array.from(holidayEntries.values())
    .sort((a, b) => a.startsOn.localeCompare(b.startsOn) || a.name.localeCompare(b.name))
    .reduce<Record<number, OverviewEntry[]>>((groups, entry) => {
      (groups[entry.year] ||= []).push(entry);
      return groups;
    }, {});
  function isAlreadyPlanned(entry: OverviewEntry) {
    const selectedChild = Number(childId);
    if (!selectedChild) return false;
    const inDraft = planningItems.some(
      (item) =>
        item.child_id === selectedChild &&
        item.name === entry.name &&
        item.starts_on === entry.startsOn &&
        item.ends_on === entry.endsOn,
    );
    if (inDraft) return true;
    const inPendingRequest = pendingPlanning.some((request) =>
      (request.proposed_data.items || []).some((item) => {
        const startsOn = localDateTime(new Date(item.starts_at)).slice(0, 10),
          endsOn = localDateTime(new Date(new Date(item.ends_at).getTime() - 1)).slice(0, 10);
        return item.child_id === selectedChild && item.name === entry.name && startsOn === entry.startsOn && endsOn === entry.endsOn;
      }),
    );
    if (inPendingRequest) return true;
    return plannedStays.some((stay) => {
      const startsOn = localDateTime(new Date(stay.starts_at)).slice(0, 10),
        inclusiveEnd = new Date(new Date(stay.ends_at).getTime() - 1),
        endsOn = localDateTime(inclusiveEnd).slice(0, 10);
      return (
        stay.note === entry.name &&
        startsOn === entry.startsOn &&
        endsOn === entry.endsOn
      );
    });
  }
  function addEntry(entry: OverviewEntry) {
    const planKind: PlanningItem["kind"] = entry.kind === "FEIERTAG"
      ? "FEIERTAG"
      : entry.kind === "SCHULE"
        ? /brück/i.test(entry.name) ? "BRUECKENTAG" : "FREI"
        : "FERIEN";
    onPlan({
      name: entry.name,
      starts_on: entry.startsOn,
      ends_on: entry.endsOn,
      child_id: Number(childId) || null,
      kind: planKind,
    });
  }
  return (
    <>
      <header className="pagehead">
        <div>
          <span className="eyebrow">
            Freie Tage {year}–{year + 4}
          </span>
          <h1>Ferien & Feiertage</h1>
          <p>Ferien, gesetzliche Feiertage und schulindividuelle freie Tage chronologisch nach Jahr.</p>
        </div>
        <div className="holidayfilters">
          <label className="statepick">
            Kind
            <select
              value={childId}
              onChange={(e) => selectChild(e.target.value)}
            >
              <option value="">Alle / ohne Kind</option>
              {children.map((child) => (
                <option value={child.id} key={child.id}>
                  {child.display_name}
                </option>
              ))}
            </select>
          </label>
          <label className="statepick">
            Bundesland
            <select value={state} onChange={(e) => setState(e.target.value)}>
              {[
                ["BW", "Baden-Württemberg"],
                ["BY", "Bayern"],
                ["BE", "Berlin"],
                ["BB", "Brandenburg"],
                ["HB", "Bremen"],
                ["HH", "Hamburg"],
                ["HE", "Hessen"],
                ["MV", "Mecklenburg-Vorpommern"],
                ["NI", "Niedersachsen"],
                ["NW", "Nordrhein-Westfalen"],
                ["RP", "Rheinland-Pfalz"],
                ["SL", "Saarland"],
                ["SN", "Sachsen"],
                ["ST", "Sachsen-Anhalt"],
                ["SH", "Schleswig-Holstein"],
                ["TH", "Thüringen"],
              ].map(([v, n]) => (
                <option value={v} key={v}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>
      {error && <p className="error">{error}</p>}
      {!childId && (
        <p className="holidayhint">Wähle ein Kind aus, um auch schulindividuelle Brücken- und freie Tage anzuzeigen.</p>
      )}
      {Object.entries(entriesByYear).map(([entryYear, entries]) => (
        <section className="holidayyear" key={entryYear}>
          <header>
            <h2>{entryYear}</h2>
          </header>
          <div className="holidaylist">
            {entries.map((entry) => {
              const date = new Date(`${entry.startsOn}T12:00:00`),
                bridgeDate = entry.kind === "FEIERTAG"
                  ? date.getDay() === 4
                    ? new Date(date.getFullYear(), date.getMonth(), date.getDate() + 1)
                    : date.getDay() === 2
                      ? new Date(date.getFullYear(), date.getMonth(), date.getDate() - 1)
                      : null
                  : null,
                alreadyPlanned = isAlreadyPlanned(entry);
              return (
                <article key={entry.key}>
                  {entry.kind === "FERIEN" ? <Palmtree /> : <CalendarDays />}
                  <div>
                    <h3>{entry.name} <span className="tag">{entry.kind === "FERIEN" ? "Ferien" : entry.kind === "FEIERTAG" ? "Feiertag" : "Schulkalender"}</span></h3>
                    <p>{date.toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit", year: "numeric" })}{entry.endsOn !== entry.startsOn ? ` – ${new Date(`${entry.endsOn}T12:00:00`).toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit", year: "numeric" })}` : ""}</p>
                    {bridgeDate && <small>Möglicher Brückentag: {bridgeDate.toLocaleDateString("de-DE")}</small>}
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      ))}
    </>
  );
}

function PlanningScreen({
  items,
  children,
  people,
  onChange,
}: {
  items: PlanningItem[];
  children: Child[];
  people: User[];
  onChange: (items: PlanningItem[]) => void;
}) {
  const [error, setError] = useState(""),
    [sourceChildId, setSourceChildId] = useState(""),
    [sourceYear, setSourceYear] = useState(new Date().getFullYear()),
    [sourceHolidays, setSourceHolidays] = useState<Holiday[]>([]),
    [sourcePublic, setSourcePublic] = useState<Holiday[]>([]),
    [sourceBusy, setSourceBusy] = useState(false),
    [dragActive, setDragActive] = useState(false),
    [splitId, setSplitId] = useState<string | null>(null),
    [splitStart, setSplitStart] = useState(""),
    [splitTime, setSplitTime] = useState("10:00"),
    [splitPersonId, setSplitPersonId] = useState(""),
    [planTitle, setPlanTitle] = useState("Ferien- und Jahresplanung"),
    [recipientId, setRecipientId] = useState(""),
    [submitting, setSubmitting] = useState(false),
    [success, setSuccess] = useState("");
  useEffect(() => {
    if (!sourceChildId && children.length === 1)
      setSourceChildId(String(children[0].id));
  }, [children.length, sourceChildId]);
  useEffect(() => {
    const child = children.find((entry) => entry.id === Number(sourceChildId));
    if (!child) return;
    const state = child.school_state_code || "HE";
    setSourceBusy(true);
    Promise.all([
      api<Holiday[]>(`/holidays?year=${sourceYear}&state=${state}`),
      api<Holiday[]>(`/public-holidays?year=${sourceYear}&state=${state}`),
    ])
      .then(([holidays, publicHolidays]) => {
        setSourceHolidays(holidays);
        setSourcePublic(publicHolidays);
      })
      .catch((x) => setError((x as Error).message))
      .finally(() => setSourceBusy(false));
  }, [sourceChildId, sourceYear, children.length]);
  function addSource(item: Holiday, kind: PlanningItem["kind"]) {
    setError("");
    if (sourceInDraft(item)) {
      setError("Dieser Zeitraum ist bereits im aktuellen Planungsentwurf enthalten.");
      return;
    }
    onChange([
      ...items,
      {
        ...item,
        id: clientId(),
        kind,
        child_id: Number(sourceChildId) || null,
        responsible_user_id: null,
        starts_time: "",
        ends_time: "",
      },
    ]);
  }
  function sourceInDraft(item: Holiday) {
    const selectedChild = Number(sourceChildId) || null;
    return items.some((entry) =>
      entry.child_id === selectedChild && entry.name === item.name &&
      entry.starts_on === item.starts_on && entry.ends_on === item.ends_on
    );
  }
  function dragSource(event: React.DragEvent, item: Holiday, kind: PlanningItem["kind"]) {
    event.dataTransfer.effectAllowed = "copy";
    const value = JSON.stringify({ item, kind });
    event.dataTransfer.setData("application/x-familienplan", value);
    event.dataTransfer.setData("text/plain", value);
  }
  function dropSource(event: React.DragEvent) {
    event.preventDefault();
    setDragActive(false);
    try {
      const transferred =
        event.dataTransfer.getData("application/x-familienplan") ||
        event.dataTransfer.getData("text/plain");
      const value = JSON.parse(transferred);
      if (value?.item && value?.kind) addSource(value.item, value.kind);
    } catch {
      setError("Der Zeitraum konnte nicht übernommen werden.");
    }
  }
  function addCustom(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const starts_on = String(form.get("starts_on"));
    const ends_on = String(form.get("ends_on"));
    const starts_time = String(form.get("starts_time") || "");
    const ends_time = String(form.get("ends_time") || "");
    if (ends_on < starts_on) {
      setError("Das Ende muss am oder nach dem Beginn liegen.");
      return;
    }
    setError("");
    onChange([
      ...items,
      {
        id: clientId(),
        name: String(form.get("name")) || "Freier Planungszeitraum",
        starts_on,
        ends_on,
        child_id: Number(form.get("child_id")) || null,
        responsible_user_id: Number(form.get("responsible_user_id")) || null,
        starts_time,
        ends_time,
        kind: "FREI",
      },
    ]);
    e.currentTarget.reset();
  }
  function update(id: string, change: Partial<PlanningItem>) {
    onChange(items.map((item) => item.id === id ? { ...item, ...change } : item));
  }
  function beginSplit(item: PlanningItem) {
    setSplitId(item.id);
    const starts = new Date(`${item.starts_on}T12:00:00`);
    const ends = new Date(`${item.ends_on}T12:00:00`);
    const middle = new Date(starts.getTime() + (ends.getTime() - starts.getTime()) / 2);
    setSplitStart(`${middle.getFullYear()}-${String(middle.getMonth() + 1).padStart(2, "0")}-${String(middle.getDate()).padStart(2, "0")}`);
    setSplitTime("10:00");
    setSplitPersonId(item.responsible_user_id ? String(item.responsible_user_id) : "");
    setError("");
  }
  function applySplit(item: PlanningItem) {
    const originalStart = new Date(`${item.starts_on}T${item.starts_time || "00:00"}:00`);
    const originalEnd = new Date(`${item.ends_on}T${item.ends_time || "00:00"}:00`);
    if (!item.ends_time) originalEnd.setDate(originalEnd.getDate() + 1);
    const boundary = new Date(`${splitStart}T${splitTime || "00:00"}:00`);
    if (boundary <= originalStart || boundary >= originalEnd) {
      setError("Die Übergabe muss nach dem Beginn und vor dem Ende des Zeitraums liegen.");
      return;
    }
    const parts: PlanningItem[] = [
      {
        ...item,
        id: clientId(),
        ends_on: splitStart,
        ends_time: splitTime,
      },
      {
      ...item,
      id: clientId(),
      starts_on: splitStart,
      starts_time: splitTime,
      responsible_user_id: Number(splitPersonId) || null,
      },
    ];
    onChange(items.flatMap((entry) => entry.id === item.id ? parts : [entry]));
    setSplitId(null);
    setError("");
  }
  async function submitPlanning(mode: "direct" | "proposal") {
    if (items.some((item) => !item.child_id || !item.responsible_user_id)) {
      setError("Bitte ordne jedem Zeitraum ein Kind und eine Person zu.");
      return;
    }
    if (items.some((item) => item.ends_on < item.starts_on)) {
      setError("Bei mindestens einem Abschnitt liegt das Ende vor dem Beginn.");
      return;
    }
    if (mode === "proposal" && !recipientId) {
      setError("Bitte wähle aus, wer die Gruppenplanung bestätigen soll.");
      return;
    }
    const dateTime = (value: string, time: string, followingDay = false) => {
      const date = new Date(`${value}T${time || "00:00"}:00`);
      if (followingDay) date.setDate(date.getDate() + 1);
      return date.toISOString();
    };
    setSubmitting(true);
    setError("");
    setSuccess("");
    try {
      await api(`/planning-groups?mode=${mode}`, {
        method: "POST",
        body: JSON.stringify({
          title: planTitle,
          affected_user_id: mode === "proposal" ? Number(recipientId) : null,
          items: items.map((item) => ({
            child_id: item.child_id,
            responsible_user_id: item.responsible_user_id,
            starts_at: dateTime(item.starts_on, item.starts_time || ""),
            ends_at: dateTime(item.ends_on, item.ends_time || "", !item.ends_time),
            name: item.name,
            kind: item.kind,
          })),
        }),
      });
      setSuccess(mode === "direct" ? "Die Planung wurde direkt in den Kalender übernommen." : "Die Gruppenanfrage wurde gesendet.");
      onChange([]);
    } catch (x) {
      setError((x as Error).message);
    } finally {
      setSubmitting(false);
    }
  }
  return (
    <>
      <header className="pagehead">
        <div>
          <span className="eyebrow">Gemeinsamer Entwurf</span>
          <h1>Planung zusammenstellen</h1>
          <p>Mehrere Ferien, Feiertage und freie Zeiträume in einer Planung sammeln.</p>
        </div>
      </header>
      <section className="planningsources">
        <div className="planningsourcehead">
          <div><h2>Ferien und Feiertage</h2><p>In den Entwurf ziehen oder mit „Hinzufügen“ übernehmen.</p></div>
          <div className="sourcefilters">
            <label>Kind<select value={sourceChildId} onChange={(e) => setSourceChildId(e.target.value)}>{children.map((child) => <option key={child.id} value={child.id}>{child.display_name}</option>)}</select></label>
            <label>Jahr<select value={sourceYear} onChange={(e) => setSourceYear(Number(e.target.value))}>{Array.from({ length: 5 }, (_, index) => new Date().getFullYear() + index).map((year) => <option key={year}>{year}</option>)}</select></label>
          </div>
        </div>
        {sourceBusy ? <p className="muted">Ferien und Feiertage werden geladen …</p> : (
          <div className="sourcecolumns">
            <details open>
              <summary>Schulferien <span>{sourceHolidays.length}</span></summary>
              <div className="sourcecards">{sourceHolidays.map((item) => { const used=sourceInDraft(item); return <article className={used?"in-draft":""} key={`${item.name}-${item.starts_on}`} draggable={!used} onDragStart={(e) => !used && dragSource(e, item, "FERIEN")}><div><strong>{item.name}</strong><small>{new Date(`${item.starts_on}T12:00`).toLocaleDateString("de-DE")} – {new Date(`${item.ends_on}T12:00`).toLocaleDateString("de-DE")}</small></div><button disabled={used} onClick={() => addSource(item, "FERIEN")}>{used?"Im Entwurf":"Hinzufügen"}</button></article>})}</div>
            </details>
            <details open>
              <summary>Feiertage <span>{sourcePublic.length}</span></summary>
              <div className="sourcecards">{sourcePublic.map((item) => { const used=sourceInDraft(item); return <article className={used?"in-draft":""} key={`${item.name}-${item.starts_on}`} draggable={!used} onDragStart={(e) => !used && dragSource(e, item, "FEIERTAG")}><div><strong>{item.name}</strong><small>{new Date(`${item.starts_on}T12:00`).toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" })}</small></div><button disabled={used} onClick={() => addSource(item, "FEIERTAG")}>{used?"Im Entwurf":"Hinzufügen"}</button></article>})}</div>
            </details>
          </div>
        )}
      </section>
      <section className="planningcomposer">
        <h2>Freien Zeitraum hinzufügen</h2>
        {error && <p className="error">{error}</p>}
        <form onSubmit={addCustom} className="planningform">
          <Field label="Bezeichnung" name="name" required={false} />
          <label>Kind<select name="child_id" required defaultValue={children.length === 1 ? children[0].id : ""}><option value="" disabled>Bitte auswählen</option>{children.map((child) => <option key={child.id} value={child.id}>{child.display_name}</option>)}</select></label>
          <label>Vorgesehen bei<select name="responsible_user_id" defaultValue=""><option value="">Noch offen</option>{people.map((person) => <option key={person.id} value={person.id}>{person.display_name}</option>)}</select></label>
          <Field label="Von" name="starts_on" type="date" />
          <Field label="Uhrzeit von (optional)" name="starts_time" type="time" required={false} />
          <Field label="Bis" name="ends_on" type="date" />
          <Field label="Uhrzeit bis (optional)" name="ends_time" type="time" required={false} />
          <button><Plus size={18} /> Zum Entwurf</button>
        </form>
      </section>
      <section
        className={`planningdraft ${dragActive ? "dragactive" : ""}`}
        onDragEnter={(event) => { event.preventDefault(); setDragActive(true); }}
        onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; }}
        onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragActive(false); }}
        onDrop={dropSource}
      >
        <div className="planningdrafthead">
          <div><h2>Planungsentwurf</h2><p>{items.length} {items.length === 1 ? "Zeitraum" : "Zeiträume"} gesammelt</p></div>
          {items.length > 0 && <button className="secondary" onClick={() => onChange([])}>Entwurf leeren</button>}
        </div>
        {!items.length && <p className="emptyplanning">Ferien oder Feiertage hierher ziehen – oder einen freien Zeitraum eintragen.</p>}
        {items.map((item) => (
          <article className="planningitem" key={item.id}>
            <div className="planningitemtitle"><span className="tag">{item.kind === "BRUECKENTAG" ? "Brückentag" : item.kind.charAt(0) + item.kind.slice(1).toLowerCase()}</span><strong>{item.name}</strong><small>{new Date(`${item.starts_on}T12:00:00`).toLocaleDateString("de-DE")} – {new Date(`${item.ends_on}T12:00:00`).toLocaleDateString("de-DE")}</small></div>
            <label>Kind<select value={item.child_id || ""} onChange={(e) => update(item.id, { child_id: Number(e.target.value) || null })}><option value="">Bitte auswählen</option>{children.map((child) => <option key={child.id} value={child.id}>{child.display_name}</option>)}</select></label>
            <label>Vorgesehen bei<select value={item.responsible_user_id || ""} onChange={(e) => update(item.id, { responsible_user_id: Number(e.target.value) || null })}><option value="">Noch offen</option>{people.map((person) => <option key={person.id} value={person.id}>{person.display_name}</option>)}</select></label>
            <div className="planningdates">
              <label>Von<input type="date" value={item.starts_on} max={item.ends_on} onChange={(e) => update(item.id, { starts_on: e.target.value })} /></label>
              <label>Bis<input type="date" value={item.ends_on} min={item.starts_on} onChange={(e) => update(item.id, { ends_on: e.target.value })} /></label>
            </div>
            <div className="planningtimes">
              <label>Von Uhr<input type="time" value={item.starts_time || ""} onChange={(e) => update(item.id, { starts_time: e.target.value })} /></label>
              <label>Bis Uhr<input type="time" value={item.ends_time || ""} onChange={(e) => update(item.id, { ends_time: e.target.value })} /></label>
              <small>Leer = jeweilige Tagesgrenze</small>
            </div>
            <div className="planningitemactions">
              {item.starts_on !== item.ends_on && <button className="secondary" onClick={() => beginSplit(item)}>Aufteilen</button>}
              <button className="danger secondary" onClick={() => onChange(items.filter((entry) => entry.id !== item.id))}>Entfernen</button>
            </div>
            {splitId === item.id && (
              <div className="spliteditor">
                <div><strong>Exakte Übergabe festlegen</strong><small>Der erste Teil endet und der zweite beginnt zum selben Zeitpunkt.</small></div>
                <label>Übergabe am<input type="date" value={splitStart} min={item.starts_on} max={item.ends_on} onChange={(e) => setSplitStart(e.target.value)} /></label>
                <label>Uhrzeit<input type="time" value={splitTime} onChange={(e) => setSplitTime(e.target.value)} required /></label>
                <label>Zweiter Teil bei<select value={splitPersonId} onChange={(e) => setSplitPersonId(e.target.value)}><option value="">Noch offen</option>{people.map((person) => <option key={person.id} value={person.id}>{person.display_name}</option>)}</select></label>
                <div className="splitactions"><button onClick={() => applySplit(item)}>Aufteilung übernehmen</button><button className="secondary" onClick={() => setSplitId(null)}>Abbrechen</button></div>
              </div>
            )}
          </article>
        ))}
        {items.length > 0 && (
          <div className="planningfooter">
            <div className="plansubmitfields">
              <label>Titel<input value={planTitle} onChange={(e) => setPlanTitle(e.target.value)} /></label>
              <label>Bestätigung durch<select value={recipientId} onChange={(e) => setRecipientId(e.target.value)}><option value="">Bitte auswählen</option>{people.filter((person) => person.id !== getSessionUser()?.id).map((person) => <option key={person.id} value={person.id}>{person.display_name}</option>)}</select></label>
            </div>
            <div className="plansubmitactions">
              {getSessionUser()?.role === "ADMIN" && <button disabled={submitting} onClick={() => submitPlanning("direct")}>{submitting ? "Wird übernommen …" : "Direkt übernehmen"}</button>}
              <button className={getSessionUser()?.role === "ADMIN" ? "secondary" : ""} disabled={submitting} onClick={() => submitPlanning("proposal")}>{submitting ? "Wird gesendet …" : "Als Gruppenanfrage senden"}</button>
            </div>
          </div>
        )}
        {success && <p className="success">{success}</p>}
      </section>
    </>
  );
}

function GlobalSearch({
  onSelect,
}: {
  onSelect: (result: SearchResult) => void;
}) {
  const [query, setQuery] = useState(""),
    [results, setResults] = useState<SearchResult[]>([]),
    [busy, setBusy] = useState(false),
    [focused, setFocused] = useState(false);
  useEffect(() => {
    const value = query.trim();
    if (value.length < 2) {
      setResults([]);
      setBusy(false);
      return;
    }
    let active = true;
    setBusy(true);
    const timer = window.setTimeout(() => {
      api<SearchResult[]>(`/search?q=${encodeURIComponent(value)}`, {
        background: true,
      })
        .then((items) => active && setResults(items))
        .catch(() => active && setResults([]))
        .finally(() => active && setBusy(false));
    }, 280);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [query]);
  const showResults = focused && query.trim().length >= 2;
  return (
    <div className="globalsearch">
      <Search aria-hidden="true" />
      <input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => window.setTimeout(() => setFocused(false), 160)}
        placeholder="Kinder, Personen, Termine und Betreuung suchen …"
        aria-label="FamilienPlan durchsuchen"
      />
      {query && (
        <button
          aria-label="Suche leeren"
          onClick={() => {
            setQuery("");
            setResults([]);
          }}
        >
          ×
        </button>
      )}
      {showResults && (
        <section className="searchresults">
          {busy ? (
            <p>Suche läuft …</p>
          ) : results.length ? (
            results.map((result) => (
              <button
                key={`${result.kind}-${result.id}`}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => {
                  onSelect(result);
                  setFocused(false);
                }}
              >
                <span className={`searchkind ${result.kind}`}>
                  {result.kind === "event"
                    ? "Termin"
                    : result.kind === "stay"
                      ? "Betreuung"
                      : result.kind === "child"
                        ? "Kind"
                        : result.kind === "birthday"
                          ? "Geburtstag"
                          : "Person"}
                </span>
                <span>
                  <strong>{result.title}</strong>
                  <small>
                    {result.starts_at
                      ? `${new Date(result.starts_at).toLocaleString("de-DE")} · `
                      : ""}
                    {result.subtitle}
                  </small>
                </span>
                <ChevronRight size={17} />
              </button>
            ))
          ) : (
            <p>Keine Treffer gefunden.</p>
          )}
        </section>
      )}
    </div>
  );
}

function App() {
  const [loading, setLoading] = useState(true),
    [setup, setSetup] = useState(false),
    [user, setUser] = useState<User | null>(null),
    [impersonating, setImpersonating] = useState(false),
    [screen, setScreen] = useState<Screen>(() => {
      if (new URLSearchParams(location.search).has("request")) return "calendar";
      const stored = localStorage.getItem("familienplan.lastScreen");
      return stored && stored in labels ? (stored as Screen) : "home";
    }),
    [children, setChildren] = useState<Child[]>([]),
    [people, setPeople] = useState<User[]>([]),
    [sectionAccess, setSectionAccess] = useState<SectionAccess>({ birthdays: [], waste_collection: [] }),
    [notifications, setNotifications] = useState<AppNotification[]>([]),
    [notificationsOpen, setNotificationsOpen] = useState(false),
    [mobileMenuOpen, setMobileMenuOpen] = useState(false),
    [meta, setMeta] = useState<ApplicationMeta | null>(null),
    [updateStarting, setUpdateStarting] = useState(false),
    [updateDialog, setUpdateDialog] = useState<"confirm" | "progress" | "timeout" | "error" | null>(null),
    [updateError, setUpdateError] = useState(""),
    [updateSeconds, setUpdateSeconds] = useState(30),
    [showChangelog, setShowChangelog] = useState(false),
    [markingNotificationsRead, setMarkingNotificationsRead] = useState(false),
    [calendarTarget, setCalendarTarget] = useState<CalendarTarget | null>(null),
    [holidayDraft, setHolidayDraft] =
      useState<HolidayPlanningDraft | null>(null),
    [planningItems, setPlanningItems] = useState<PlanningItem[]>(() => {
      try {
        return JSON.parse(localStorage.getItem("familienplan.planningDraft") || "[]");
      } catch {
        return [];
      }
    });
  const loadChildren = () =>
      api<Child[]>("/children")
        .then(setChildren)
        .catch(() => {}),
    loadPeople = () =>
      api<User[]>("/people")
        .then(setPeople)
        .catch(() => {}),
    loadNotifications = () =>
      api<AppNotification[]>("/notifications", { background: true })
        .then((items) =>
          setNotifications((current) =>
            JSON.stringify(current) === JSON.stringify(items)
              ? current
              : items,
          ),
        )
        .catch(() => {});
  useEffect(() => {
    Promise.all([
      api<{ setup_required: boolean }>("/setup/status"),
      api<{ user: User; csrf_token: string; impersonating?: boolean }>("/auth/me").catch(() => null),
    ])
      .then(([s, m]) => {
        setSetup(s.setup_required);
        if (m) {
          setUser(m.user);
          setCsrf(m.csrf_token);
          setImpersonating(Boolean(m.impersonating));
        }
      })
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    if (user) {
      loadChildren();
      loadPeople();
      loadNotifications();
      api<ApplicationMeta>("/meta").then(setMeta).catch(() => null);
      api<SectionAccess>("/settings/sections").then(setSectionAccess).catch(() => {});
      api<{ primary_color: string; holiday_color: string; birthday_color: string; school_color: string }>("/settings/theme")
        .then((t) => {
          document.documentElement.style.setProperty(
            "--green",
            t.primary_color,
          );
        })
        .catch(() => {});
      api<CalendarColorPreferences>("/settings/calendar-colors")
        .then((colors) => {
          document.documentElement.style.setProperty("--holiday", colors.holiday_color);
          document.documentElement.style.setProperty("--birthday", colors.birthday_color);
          document.documentElement.style.setProperty("--school", colors.school_color);
          document.documentElement.style.setProperty("--waste", colors.waste_color);
        })
        .catch(() => {});
    }
  }, [user]);
  useEffect(() => {
    if (!user) return;
    const timer = window.setInterval(loadNotifications, 15000);
    return () => window.clearInterval(timer);
  }, [user]);
  useEffect(() => {
    if (!user) return;
    const refresh = () => {
      loadChildren(); loadPeople(); loadNotifications();
      api<SectionAccess>("/settings/sections", { background: true }).then(setSectionAccess).catch(() => {});
    };
    window.addEventListener("familienplan:data-changed", refresh);
    return () => window.removeEventListener("familienplan:data-changed", refresh);
  }, [user?.id]);
  useEffect(() => {
    localStorage.setItem("familienplan.lastScreen", screen);
  }, [screen]);
  useEffect(() => {
    localStorage.setItem("familienplan.planningDraft", JSON.stringify(planningItems));
  }, [planningItems]);
  async function installUpdate() {
    if (!meta?.update_available || updateStarting) return;
    setUpdateDialog("progress");
    setUpdateSeconds(30);
    setUpdateStarting(true);
    try {
      await api("/system/update", { method: "POST" });
      const countdown = window.setInterval(() => {
        setUpdateSeconds((current) => {
          if (current <= 1) {
            window.clearInterval(countdown);
            location.reload();
            return 0;
          }
          return current - 1;
        });
      }, 1000);
      const previousVersion = meta.version;
      const deadline = Date.now() + 5 * 60_000;
      const poll = window.setInterval(async () => {
        if (Date.now() > deadline) {
          window.clearInterval(poll);
          setUpdateStarting(false);
          setUpdateDialog("timeout");
          return;
        }
        try {
          const current = await api<ApplicationMeta>("/meta", { background: true });
          if (current.version !== previousVersion) {
            window.clearInterval(poll);
            location.reload();
          }
        } catch {
          // Während des Dienstneustarts ist die Anwendung kurz nicht erreichbar.
        }
      }, 4000);
    } catch (error) {
      setUpdateStarting(false);
      setUpdateError((error as Error).message);
      setUpdateDialog("error");
    }
  }
  useEffect(() => {
    if (!user || user.role === "ADMIN") return;
    if (screen === "people" || (screen === "birthdays" && (!user.allowed_event_types.includes("BIRTHDAY") || !sectionAccess.birthdays.includes(user.id))) || (screen === "waste" && (!user.allowed_event_types.includes("WASTE") || !sectionAccess.waste_collection.includes(user.id)))) setScreen("home");
  }, [user, screen, sectionAccess]);
  if (loading) return <div className="splash">FamilienPlan</div>;
  if (setup && !user)
    return (
      <Setup
        done={(u) => {
          setUser(u);
          setSetup(false);
        }}
      />
    );
  if (!user) return <Login done={setUser} />;
  async function logout() {
    await api("/auth/logout", { method: "POST" });
    setUser(null);
  }
  async function openNotifications() {
    await loadNotifications();
    setNotificationsOpen((value) => !value);
  }
  async function markAllNotificationsRead() {
    setMarkingNotificationsRead(true);
    try {
      await api("/notifications/read-all", { method: "POST" });
      await loadNotifications();
    } finally {
      setMarkingNotificationsRead(false);
    }
  }
  function openCalendar(target?: CalendarTarget) {
    setCalendarTarget(target || null);
    setScreen("calendar");
  }
  function openSearchResult(result: SearchResult) {
    if ((result.kind === "event" || result.kind === "stay") && result.starts_at) {
      openCalendar({
        kind: result.kind,
        id: result.id,
        startsAt: result.starts_at,
      });
      return;
    }
    if (result.kind === "birthday" && result.starts_at) {
      openCalendar({ kind: "birthday", id: result.id, startsAt: result.starts_at });
      return;
    }
    setScreen(result.kind === "person" ? "people" : "children");
  }
  const nav = ([
    ["home", Home],
    ["calendar", CalendarDays],
    ["children", Users],
    ["people", UserPlus],
    ["birthdays", Cake],
    ["waste", Trash2],
    ["holidays", Palmtree],
    ["planning", ClipboardList],
    ["settings", Palette],
  ] as const).filter(([id]) => {
    if (id === "people") return user.role === "ADMIN";
    if (id === "birthdays") return user.role === "ADMIN" || (user.allowed_event_types.includes("BIRTHDAY") && sectionAccess.birthdays.includes(user.id));
    if (id === "waste") return user.role === "ADMIN" || (user.allowed_event_types.includes("WASTE") && sectionAccess.waste_collection.includes(user.id));
    return true;
  });
  let content: React.ReactNode = (
    <Dashboard children={children} people={people} openCalendar={openCalendar} />
  );
  if (screen === "calendar")
    content = (
      <CalendarScreen
        children={children}
        people={people}
        holidayDraft={holidayDraft}
        holidayDraftConsumed={() => setHolidayDraft(null)}
        target={calendarTarget}
      />
    );
  else if (screen === "children")
    content = (
      <Children items={children} reload={loadChildren} people={people} />
    );
  else if (screen === "people" && user.role === "ADMIN")
    content = <PeopleScreen people={people} reload={loadPeople} />;
  else if (screen === "birthdays") content = <BirthdaysScreen />;
  else if (screen === "waste") content = <WasteCollectionScreen people={people} children={children} />;
  else if (screen === "holidays")
    content = (
      <HolidaysScreen
        children={children}
        planningItems={planningItems}
        onPlan={(draft) => {
          setPlanningItems((current) => [
            ...current,
            {
              ...draft,
              id: clientId(),
              responsible_user_id: null,
            },
          ]);
        }}
      />
    );
  else if (screen === "planning")
    content = (
      <PlanningScreen
        items={planningItems}
        children={children}
        people={people}
        onChange={setPlanningItems}
      />
    );
  else if (screen === "settings")
    content = <SettingsScreen user={user} people={people} onUserChange={setUser} sectionAccess={sectionAccess} onSectionAccessChange={setSectionAccess} updateMeta={meta} onCheckForUpdates={async () => { const current = await api<ApplicationMeta>("/meta?refresh=true"); setMeta(current); return current; }} />;
  const unreadDecisions = notifications.filter(
    (item) =>
      !item.read_at &&
      ["STAY_APPROVED", "STAY_REJECTED", "STAY_COUNTER"].includes(item.kind),
  );
  return (
    <div className="shell">
      {impersonating && (
        <div className="impersonation-banner">
          <span>Ansicht als <strong>{user.display_name}</strong></span>
          <button onClick={async () => {
            const original = await api<{ user: User; csrf_token: string }>("/auth/impersonation/stop", { method: "POST" });
            setUser(original.user);
            setCsrf(original.csrf_token);
            setImpersonating(false);
            location.reload();
          }}>Zurück zum Admin</button>
        </div>
      )}
      <aside className="sidebar">
        <div className="brand">
          <div className="mark">FP</div>
          <div className="brand-copy">
            <b>FamilienPlan</b>
            <button type="button" className="brand-version" onClick={() => setShowChangelog(true)} disabled={!meta} title={meta?.update_check_error || "Änderungsprotokoll anzeigen"}>
              Version {meta?.version || "…"}
            </button>
            {meta?.update_available && user.role === "ADMIN" && !impersonating && (
              <button className="brand-update" type="button" onClick={() => setUpdateDialog("confirm")} disabled={updateStarting}>
                {updateStarting ? "Update wird installiert …" : `Update ${meta.latest_version} installieren`}
              </button>
            )}
          </div>
        </div>
        <nav>
          {nav.map(([id, Icon]) => (
            <button
              className={screen === id ? "active" : ""}
              onClick={() => {
                setCalendarTarget(null);
                setScreen(id);
              }}
              key={id}
            >
              <Icon />
              {labels[id]}
            </button>
          ))}
        </nav>
        <div className="profile">
          <div className="avatar">{user.display_name[0]}</div>
          <div>
            <b>{user.display_name}</b>
            <small>
              {user.role === "ADMIN" ? "Administrator" : "Mitglied"}
            </small>
          </div>
          <button onClick={logout} title="Abmelden">
            <LogOut />
          </button>
        </div>
      </aside>
      {updateDialog && (
        <div className="modal update-dialog" role="dialog" aria-modal="true" aria-labelledby="update-dialog-title">
          <section className="panel">
            <button type="button" className="close" onClick={() => setUpdateDialog(null)} aria-label="Schließen">×</button>
            <h2 id="update-dialog-title">
              {updateDialog === "confirm" ? "Update installieren" : updateDialog === "progress" ? "Update wird installiert" : "Update nicht abgeschlossen"}
            </h2>
            {updateDialog === "confirm" ? (
              <p>FamilienPlan {meta?.latest_version} jetzt installieren? Vorher wird automatisch ein Backup erstellt.</p>
            ) : updateDialog === "progress" ? (
              <><p>Backup, Aktualisierung und Neustart laufen. FamilienPlan lädt anschließend automatisch neu.</p><div className="update-countdown"><strong>{updateSeconds}</strong><span>Sekunden bis zum Neuladen</span></div></>
            ) : updateDialog === "timeout" ? (
              <p>Das Update dauert länger als erwartet. Prüfe auf dem Server den Status mit <code>systemctl status familienplan-update.service</code>.</p>
            ) : (
              <p className="error">{updateError || "Das Update konnte nicht gestartet werden."}</p>
            )}
            <div className="dialog-actions">
              {updateDialog === "confirm" ? (
                <>
                  <button type="button" className="secondary" onClick={() => setUpdateDialog(null)}>Abbrechen</button>
                  <button type="button" onClick={installUpdate}>Update installieren</button>
                </>
              ) : updateDialog !== "progress" ? (
                <button type="button" onClick={() => setUpdateDialog(null)}>Schließen</button>
              ) : null}
            </div>
          </section>
        </div>
      )}
      {showChangelog && meta && <ChangelogModal meta={meta} onClose={() => setShowChangelog(false)} />}
      <button
        className="notification-toggle"
        onClick={openNotifications}
        aria-label="Benachrichtigungen"
      >
        <Bell />
        {notifications.some((item) => !item.read_at) && <i />}
      </button>
      {notificationsOpen && (
        <section className="notification-panel">
          <header>
            <h2>Benachrichtigungen</h2>
            <div>
              {notifications.some((item) => !item.read_at) && (
                <button
                  className="readall"
                  disabled={markingNotificationsRead}
                  onClick={markAllNotificationsRead}
                >
                  {markingNotificationsRead
                    ? "Wird markiert …"
                    : "Alle als gelesen"}
                </button>
              )}
              <button
                className="notification-close"
                onClick={() => setNotificationsOpen(false)}
                aria-label="Benachrichtigungen schließen"
              >
                ×
              </button>
            </div>
          </header>
          {notifications.length ? (
            notifications.map((item) => (
              <article className={item.read_at ? "" : "unread"} key={item.id}>
                <strong>{item.title}</strong>
                <p>{item.body}</p>
                <small>
                  {new Date(item.created_at).toLocaleString("de-DE")}
                </small>
                {!item.read_at && (
                  <button
                    onClick={async () => {
                      await api(`/notifications/${item.id}/read`, {
                        method: "POST",
                      });
                      loadNotifications();
                    }}
                  >
                    Als gelesen markieren
                  </button>
                )}
              </article>
            ))
          ) : (
            <p>Keine Benachrichtigungen vorhanden.</p>
          )}
        </section>
      )}
      <header className="mobiletop">
        <div className="mark">FP</div>
        <b>FamilienPlan</b>
        <button onClick={openNotifications} aria-label="Benachrichtigungen">
          <Bell />
        </button>
        <button className="mobile-logout" onClick={logout} aria-label="Abmelden" title="Abmelden">
          <LogOut /><span>Abmelden</span>
        </button>
      </header>
      <main className="content">
        <header className="globalheader">
          <GlobalSearch onSelect={openSearchResult} />
        </header>
        {unreadDecisions.length > 0 && (
          <section className="decision-notifications">
            <h2>Neue Rückmeldungen</h2>
            {unreadDecisions.map((item) => (
              <article key={item.id}>
                <div>
                  <strong>{item.title}</strong>
                  <p>{item.body}</p>
                </div>
                <button
                  onClick={async () => {
                    await api(`/notifications/${item.id}/read`, {
                      method: "POST",
                    });
                    loadNotifications();
                  }}
                >
                  Gelesen
                </button>
              </article>
            ))}
          </section>
        )}
        {content}
      </main>
      <nav className="bottom">
        {nav.filter(([id]) => id === "home" || id === "calendar").map(([id, Icon]) => (
          <button
            className={screen === id ? "active" : ""}
            onClick={() => {
              setCalendarTarget(null);
              setScreen(id);
            }}
            key={id}
          >
            <Icon />
            <small>{labels[id]}</small>
          </button>
        ))}
        <button className={!['home', 'calendar'].includes(screen) ? "active" : ""} onClick={() => setMobileMenuOpen(true)}><Menu /><small>Menü</small></button>
      </nav>
      {mobileMenuOpen && <div className="mobile-menu" role="dialog" aria-modal="true" aria-label="Navigation"><button className="mobile-menu-backdrop" onClick={() => setMobileMenuOpen(false)} aria-label="Menü schließen"/><section><header><div><strong>Menü</strong><small>Bereich auswählen</small></div><button onClick={() => setMobileMenuOpen(false)} aria-label="Menü schließen">×</button></header><nav>{nav.map(([id, Icon]) => <button className={screen === id ? "active" : ""} key={id} onClick={() => { setCalendarTarget(null); setScreen(id); setMobileMenuOpen(false); }}><Icon/><span>{labels[id]}</span></button>)}</nav></section></div>}
    </div>
  );
}
function InviteAccept() {
  const token = location.pathname.split("/invite/")[1] || "",
    [done, setDone] = useState(false),
    [error, setError] = useState("");
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.currentTarget));
    try {
      await api("/invitations/accept", {
        method: "POST",
        body: JSON.stringify({ ...d, token }),
      });
      setDone(true);
      history.replaceState({}, "", "/");
    } catch (x) {
      setError((x as Error).message);
    }
  }
  if (done)
    return (
      <main className="auth">
        <section className="panel">
          <h2>Einladung angenommen</h2>
          <p>Du kannst FamilienPlan jetzt verwenden.</p>
          <button onClick={() => location.reload()}>Weiter</button>
        </section>
      </main>
    );
  return (
    <main className="auth">
      <section className="auth-copy">
        <span className="eyebrow">FamilienPlan</span>
        <h1>
          Willkommen
          <br />
          in der Familie.
        </h1>
      </section>
      <form className="panel" onSubmit={submit}>
        <h2>Einladung annehmen</h2>
        {error && <p className="error">{error}</p>}
        <Field label="E-Mail-Adresse" name="email" type="email" />
        <Field label="Benutzername" name="username" />
        <Field label="Anzeigename" name="display_name" />
        <div className="grid2">
          <Field label="Vorname" name="first_name" required={false} />
          <Field label="Nachname" name="last_name" required={false} />
        </div>
        <Field
          label="Passwort (mindestens 12 Zeichen)"
          name="password"
          type="password"
        />
        <Field
          label="Passwort bestätigen"
          name="password_confirm"
          type="password"
        />
        <button>Einladung annehmen</button>
      </form>
    </main>
  );
}

function SectionAccessSettings({ people, value, onChange }: { people: User[]; value: SectionAccess; onChange: (value: SectionAccess) => void }) {
  const [draft, setDraft] = useState<SectionAccess>(value), [open, setOpen] = useState<keyof SectionAccess | null>(null), [message, setMessage] = useState(""), [error, setError] = useState("");
  useEffect(() => setDraft(value), [value.birthdays.join(","), value.waste_collection.join(",")]);
  const sectionLabels: Record<keyof SectionAccess, string> = { birthdays: "Geburtstage", waste_collection: "Abfallkalender" };
  async function save() {
    try { const saved = await api<SectionAccess>("/settings/sections", { method: "PUT", body: JSON.stringify(draft) }); onChange(saved); setMessage("Rubrikenfreigaben gespeichert."); setError(""); }
    catch (x) { setError((x as Error).message); }
  }
  return <section id="settings-access" className="themebox section-access-settings settings-card"><h2>Rubriken freigeben</h2><p className="muted">Administratoren sehen alle Rubriken. Hier wählst du weitere Personen aus.</p>{error && <p className="error">{error}</p>}{message && <p className="success">{message}</p>}
    {(Object.keys(sectionLabels) as Array<keyof SectionAccess>).map((section) => <div className="integration-row" key={section}><span><strong>{sectionLabels[section]}</strong><small>{draft[section].length ? `${draft[section].length} Person(en) freigegeben` : "Nur Administratoren"}</small></span><button type="button" className="secondary" onClick={() => setOpen(section)}>Personen auswählen</button></div>)}
    <button onClick={save}>Freigaben speichern</button>
    {open && <div className="modal"><section className="panel"><button type="button" className="close" onClick={() => setOpen(null)}>×</button><h2>{sectionLabels[open]} freigeben</h2><div className="audience-list">{people.filter((person) => person.role !== "ADMIN").map((person) => <label key={person.id}><input type="checkbox" checked={draft[open].includes(person.id)} onChange={(event) => setDraft((current) => ({ ...current, [open]: event.target.checked ? [...current[open], person.id] : current[open].filter((id) => id !== person.id) }))}/><span>{person.display_name}</span></label>)}</div><button type="button" className="audience-done" onClick={() => setOpen(null)}>Fertig</button></section></div>}
  </section>;
}

function CalendarSourceOverview() {
  const [sources, setSources] = useState<CalendarSourceStatus[]>([]), [error, setError] = useState(""), [message, setMessage] = useState(""), [syncing, setSyncing] = useState<number | null>(null);
  const load = () => api<CalendarSourceStatus[]>("/calendar-sources/status").then(setSources).catch((x) => setError((x as Error).message));
  useEffect(() => { void load(); }, []);
  async function sync(source: CalendarSourceStatus) {
    setSyncing(source.id); setError(""); setMessage("");
    try {
      const result = await api<{ message?: string; imported?: number }>(`/calendar-sources/${source.id}/sync`, { method: "POST" });
      setMessage(result.message || `${source.name} wurde synchronisiert.`);
      await load();
    } catch (x) { setError((x as Error).message); }
    finally { setSyncing(null); }
  }
  return <section id="settings-sources" className="sync-overview settings-card settings-wide"><h2>Externe Kalender</h2><p className="muted">Synchronisationsstatus aller angebundenen Kalenderquellen.</p>{error && <p className="error">{error}</p>}{message && <p className="success">{message}</p>}{!error && !sources.length && <p className="hint">Noch keine externe Kalenderquelle eingerichtet.</p>}{sources.map((source) => <article key={source.id}><div><strong>{source.name}</strong><small>{source.kind === "WASTE" ? "Abfallkalender" : source.kind === "SCHOOL" ? "Schulkalender" : source.kind}</small></div><div className="sync-source-actions"><span>{source.last_sync_at ? `Zuletzt: ${new Date(source.last_sync_at).toLocaleString("de-DE")}` : "Noch nicht synchronisiert"}</span>{source.last_error && <small className="error">{source.last_error}</small>}<button type="button" onClick={() => sync(source)} disabled={syncing !== null}>{syncing === source.id ? "Synchronisiere …" : "Jetzt synchronisieren"}</button></div></article>)}</section>;
}

type AuditEntry = { id:number; user_id:number|null; user_name:string; action:string; target_type:string|null; target_id:string|null; details:Record<string,unknown>; ip_address:string|null; created_at:string };
const auditActionLabels: Record<string,string> = {
  PASSWORD_CHANGED:"hat das eigene Passwort geändert",
  PASSWORD_RESET_REQUESTED:"hat einen Passwort-Reset angefordert",
  PASSWORD_RESET_COMPLETED:"hat das Passwort über einen Reset-Link geändert",
  LOGIN:"hat sich angemeldet", LOGOUT:"hat sich abgemeldet", LOGIN_FAILED:"Anmeldung fehlgeschlagen",
  INITIAL_ADMIN_CREATED:"hat FamilienPlan eingerichtet", PERSON_ACCESS_CHANGED:"hat die Rechte einer Person geändert", PERSON_DELETED:"hat eine Person gelöscht",
  INVITATION_CREATED:"hat eine Einladung erstellt", INVITATION_RENEWED:"hat einen Einladungslink erneuert", INVITATION_SENT:"hat eine Einladung versendet", INVITATION_ACCEPTED:"hat eine Einladung angenommen",
  CHILD_CREATED:"hat ein Kind angelegt", CHILD_CHANGED:"hat ein Kind geändert", CHILD_PERMISSION_CHANGED:"hat Kinderrechte geändert",
  STAY_CREATED:"hat eine Betreuungszeit angelegt", STAY_CHANGED:"hat eine Betreuungszeit geändert", STAY_DELETED:"hat eine Betreuungszeit gelöscht", STAY_SERIES_CREATED:"hat eine Betreuungsserie angelegt", STAY_SERIES_CHANGED:"hat eine Betreuungsserie geändert",
  STAY_SERIES_EXTENDED:"hat eine Betreuungsserie verlängert", NEW_STAY_PROPOSED:"hat eine neue Betreuungszeit vorgeschlagen", STAY_CHANGE_PROPOSED:"hat eine Betreuungsänderung vorgeschlagen", STAY_DELETE_PROPOSED:"hat das Löschen einer Betreuungszeit vorgeschlagen", GROUP_PLAN_PROPOSED:"hat eine Gruppenplanung vorgeschlagen", GROUP_PLAN_CREATED:"hat eine Gruppenplanung übernommen",
  CALENDAR_EVENT_CREATED:"hat einen Termin angelegt", CALENDAR_EVENT_CHANGED:"hat einen Termin geändert", CALENDAR_EVENT_DELETED:"hat einen Termin gelöscht", CALENDAR_EVENT_SERIES_CREATED:"hat eine Terminserie angelegt", CALENDAR_EVENT_SERIES_CHANGED:"hat eine Terminserie geändert", CALENDAR_EVENT_SERIES_DELETED:"hat eine Terminserie gelöscht",
  BIRTHDAY_CREATED:"hat einen Geburtstag angelegt", BIRTHDAY_CHANGED:"hat einen Geburtstag geändert", BIRTHDAY_DELETED:"hat einen Geburtstag gelöscht",
  SECTION_ACCESS_CHANGED:"hat Rubrikenfreigaben geändert", THEME_CHANGED:"hat die globale Darstellung geändert", PERSONAL_CALENDAR_COLORS_CHANGED:"hat persönliche Kalenderfarben geändert", OWN_PROFILE_CHANGED:"hat das eigene Profil geändert",
  SCHOOL_CALENDAR_SYNCED:"hat einen Schulkalender synchronisiert", WASTE_CALENDAR_SYNCED:"hat den Abfallkalender synchronisiert", CALENDAR_SOURCE_SYNCED:"hat einen externen Kalender synchronisiert", WASTE_CALENDAR_SETTINGS_CHANGED:"hat den Abfallkalender eingerichtet",
  SYSTEM_UPDATE_REQUESTED:"hat ein Systemupdate gestartet", IMPERSONATION_STARTED:"hat die Ansicht einer Person übernommen", IMPERSONATION_STOPPED:"hat die übernommene Ansicht beendet",
};
const auditTargetLabels:Record<string,string>={user:"Person",child:"Kind",stay:"Betreuungszeit",recurrence_rule:"Betreuungsserie",calendar_event:"Termin",calendar_event_series:"Terminserie",birthday:"Geburtstag",invitation:"Einladung",change_request:"Anfrage",calendar_source:"Kalenderquelle",setting:"Einstellung",system:"System",username:"Benutzername"};
const auditDetailLabels:Record<string,string>={title:"Titel",name:"Name",display_name:"Anzeigename",event_type:"Terminart",starts_at:"Beginn",ends_at:"Ende",birth_date:"Geburtsdatum",description:"Beschreibung",note:"Notiz",scope:"Umfang",affected:"Betroffene Einträge",occurrences:"Einträge",children:"Freigegebene Kinder",role:"Rolle",email:"E-Mail-Adresse",user_id:"Person",responsible_user_id:"Zuständige Person",child_id:"Kind",from_version:"Ausgangsversion",removed:"Entfernt",events:"Termine",visibility:"Sichtbar für",changed_values:"Geänderte Werte"};

function AuditLogSettings({ people }: { people: User[] }) {
  const [items,setItems] = useState<AuditEntry[]>([]), [userFilter,setUserFilter] = useState(""), [actionFilter,setActionFilter] = useState(""), [offset,setOffset] = useState(0), [hasMore,setHasMore] = useState(false), [busy,setBusy] = useState(false), [error,setError] = useState("");
  async function load(nextOffset=0, append=false) {
    setBusy(true); setError("");
    const query = new URLSearchParams({ limit:"100", offset:String(nextOffset) });
    if (userFilter) query.set("user_id",userFilter);
    if (actionFilter) query.set("action",actionFilter);
    try { const result = await api<{items:AuditEntry[];has_more:boolean;next_offset:number}>(`/audit-log?${query}`); setItems((current)=>append?[...current,...result.items]:result.items); setOffset(result.next_offset); setHasMore(result.has_more); }
    catch (x) { setError((x as Error).message); }
    finally { setBusy(false); }
  }
  useEffect(()=>{ void load(); },[userFilter,actionFilter]);
  const actions = [...new Set(items.map((item)=>item.action))].sort();
  return <section id="settings-audit" className="themebox settings-card settings-wide audit-log">
    <div className="audit-heading"><div><h2>Logbuch</h2><p className="muted">Sicherheits- und Änderungsverlauf aller Personen. Geheimnisse und Passwörter werden nicht protokolliert.</p></div><button type="button" className="secondary" onClick={()=>load()} disabled={busy}>{busy?"Lädt …":"Neu laden"}</button></div>
    <div className="audit-filters"><label>Person<select value={userFilter} onChange={(e)=>setUserFilter(e.target.value)}><option value="">Alle Personen</option>{people.map((person)=><option key={person.id} value={person.id}>{person.display_name}</option>)}</select></label><label>Aktivität<select value={actionFilter} onChange={(e)=>setActionFilter(e.target.value)}><option value="">Alle Aktivitäten</option>{actions.map((action)=><option key={action} value={action}>{auditActionLabels[action]||action}</option>)}</select></label></div>
    {error&&<p className="error">{error}</p>}
    <div className="audit-list">{items.map((item)=><article key={item.id}><div className="audit-time"><strong>{new Date(item.created_at).toLocaleDateString("de-DE")}</strong><span>{new Date(item.created_at).toLocaleTimeString("de-DE")}</span></div><div className="audit-event"><p><strong>{item.user_name}</strong> {auditActionLabels[item.action]||item.action.toLocaleLowerCase("de-DE").replaceAll("_"," ")}.</p><small>{item.target_type ? `${auditTargetLabels[item.target_type]||item.target_type} ${item.target_id||""}` : "System"}{item.ip_address?` · IP ${item.ip_address}`:""}</small>{Object.keys(item.details||{}).length>0&&<details><summary>Details anzeigen</summary><dl>{Object.entries(item.details).map(([key,value])=><div key={key}><dt>{auditDetailLabels[key]||key.replaceAll("_"," ")}</dt><dd>{typeof value==="object"?JSON.stringify(value):String(value)}</dd></div>)}</dl></details>}</div></article>)}</div>
    {!busy&&!items.length&&<p className="hint">Für diese Auswahl sind noch keine Aktivitäten protokolliert.</p>}
    {hasMore&&<button type="button" onClick={()=>load(offset,true)} disabled={busy}>{busy?"Lädt …":"Weitere Aktivitäten laden"}</button>}
  </section>;
}

function SettingsScreen({
  user,
  people,
  onUserChange,
  sectionAccess,
  onSectionAccessChange,
  updateMeta,
  onCheckForUpdates,
}: {
  user: User;
  people: User[];
  onUserChange: (user: User) => void;
  sectionAccess: SectionAccess;
  onSectionAccessChange: (value: SectionAccess) => void;
  updateMeta: ApplicationMeta | null;
  onCheckForUpdates: () => Promise<ApplicationMeta>;
}) {
  const [color, setColor] = useState(
      getComputedStyle(document.documentElement)
        .getPropertyValue("--green")
        .trim() || "#3BA4E5",
    ),
    [holidayColor, setHolidayColor] = useState("#78B98B"),
    [birthdayColor, setBirthdayColor] = useState("#E0A526"),
    [schoolColor, setSchoolColor] = useState("#3979B8"),
    [calendarColors, setCalendarColors] = useState<CalendarColorPreferences>({ holiday_color: "#78B98B", birthday_color: "#E0A526", school_color: "#3979B8", waste_color: "#5C8B58" }),
    [personColor, setPersonColor] = useState(user.color || "#3BA4E5"),
    [birthDate, setBirthDate] = useState(user.birth_date || ""),
    [saved, setSaved] = useState(false),
    [checkingUpdates, setCheckingUpdates] = useState(false),
    [updateCheckMessage, setUpdateCheckMessage] = useState(""),
    [settingsSection, setSettingsSection] = useState<"profile" | "calendar" | "access" | "sources" | "updates" | "integrations" | "audit" | "appearance">("profile"),
    [error, setError] = useState("");
  async function changePassword(e:FormEvent<HTMLFormElement>){e.preventDefault();setError("");setSaved(false);const form=e.currentTarget,f=new FormData(form);try{await api("/profile/password",{method:"PUT",body:JSON.stringify({current_password:f.get("current_password"),password:f.get("password"),password_confirm:f.get("password_confirm")})});form.reset();setSaved(true)}catch(x){setError((x as Error).message)}}
  useEffect(() => {
    api<{ primary_color: string; holiday_color: string; birthday_color: string; school_color: string }>(
      "/settings/theme",
    ).then((r) => {
      setColor(r.primary_color);
      setHolidayColor(r.holiday_color);
      setBirthdayColor(r.birthday_color);
      setSchoolColor(r.school_color);
      document.documentElement.style.setProperty("--green", r.primary_color);
    });
    api<CalendarColorPreferences>("/settings/calendar-colors").then((colors) => {
      setCalendarColors(colors);
      document.documentElement.style.setProperty("--holiday", colors.holiday_color);
      document.documentElement.style.setProperty("--birthday", colors.birthday_color);
      document.documentElement.style.setProperty("--school", colors.school_color);
      document.documentElement.style.setProperty("--waste", colors.waste_color);
    });
  }, []);
  function preview(value: string) {
    setColor(value);
    setSaved(false);
    document.documentElement.style.setProperty("--green", value);
  }
  async function save() {
    setError("");
    try {
      await api("/settings/theme", {
        method: "PUT",
        body: JSON.stringify({
          primary_color: color,
          holiday_color: holidayColor,
          birthday_color: birthdayColor,
          school_color: schoolColor,
        }),
      });
      setSaved(true);
    } catch (x) {
      setError((x as Error).message);
    }
  }
  async function savePersonColor() {
    setError("");
    try {
      const changed = await api<User>("/profile", {
        method: "PUT",
        body: JSON.stringify({
          color: personColor,
          birth_date: birthDate || null,
        }),
      });
      onUserChange(changed);
      setSaved(true);
    } catch (x) {
      setError((x as Error).message);
    }
  }
  async function saveCalendarColors() {
    setError("");
    try {
      const changed = await api<CalendarColorPreferences>("/settings/calendar-colors", { method: "PUT", body: JSON.stringify(calendarColors) });
      setCalendarColors(changed);
      document.documentElement.style.setProperty("--holiday", changed.holiday_color);
      document.documentElement.style.setProperty("--birthday", changed.birthday_color);
      document.documentElement.style.setProperty("--school", changed.school_color);
      document.documentElement.style.setProperty("--waste", changed.waste_color);
      setSaved(true);
    } catch (x) { setError((x as Error).message); }
  }
  async function checkForUpdates() {
    setCheckingUpdates(true); setUpdateCheckMessage("");
    try {
      const current = await onCheckForUpdates();
      setUpdateCheckMessage(current.update_available ? `Update ${current.latest_version} ist verfügbar.` : `FamilienPlan ${current.version} ist aktuell.`);
    } catch (x) { setUpdateCheckMessage((x as Error).message); }
    finally { setCheckingUpdates(false); }
  }
  return (
    <>
      <header className="pagehead">
        <div>
          <span className="eyebrow">Administration</span>
          <h1>Einstellungen</h1>
          <p>Darstellung von FamilienPlan anpassen.</p>
        </div>
      </header>
      <nav className="settings-jumps" aria-label="Einstellungsbereiche">
        <button type="button" className={settingsSection === "profile" ? "active" : ""} onClick={() => setSettingsSection("profile")}>Profil</button>
        <button type="button" className={settingsSection === "calendar" ? "active" : ""} onClick={() => setSettingsSection("calendar")}>Kalender</button>
        {user.role === "ADMIN" && <>
          <button type="button" className={settingsSection === "access" ? "active" : ""} onClick={() => setSettingsSection("access")}>Freigaben</button>
          <button type="button" className={settingsSection === "sources" ? "active" : ""} onClick={() => setSettingsSection("sources")}>Externe Kalender</button>
          <button type="button" className={settingsSection === "updates" ? "active" : ""} onClick={() => setSettingsSection("updates")}>Aktualisierungen</button>
          <button type="button" className={settingsSection === "integrations" ? "active" : ""} onClick={() => setSettingsSection("integrations")}>Integrationen</button>
          <button type="button" className={settingsSection === "audit" ? "active" : ""} onClick={() => setSettingsSection("audit")}>Logbuch</button>
          <button type="button" className={settingsSection === "appearance" ? "active" : ""} onClick={() => setSettingsSection("appearance")}>Darstellung</button>
        </>}
      </nav>
      <div className="settings-layout settings-tab-content">
      {settingsSection === "profile" && <section id="settings-profile" className="themebox settings-card">
        <h2>Meine Kalenderfarbe</h2>
        <p className="muted">
          Diese Farbe kennzeichnet im Kalender die Tage, an denen ein Kind bei
          dir ist.
        </p>
        {error && <p className="error">{error}</p>}
        {saved && <p className="success">Farbe gespeichert.</p>}
        <label>
          Mein Geburtsdatum (optional)
          <input
            type="date"
            value={birthDate}
            onChange={(e) => {
              setBirthDate(e.target.value);
              setSaved(false);
            }}
          />
        </label>
        <div className="themepicker">
          <input
            type="color"
            value={personColor}
            onChange={(e) => {
              setPersonColor(e.target.value);
              setSaved(false);
            }}
            aria-label="Eigene Kalenderfarbe auswählen"
          />
          <code>{personColor.toUpperCase()}</code>
        </div>
        <div
          className="personpreview"
          style={{
            backgroundColor: `color-mix(in srgb, ${personColor} 25%, white)`,
            borderLeftColor: personColor,
            color: personColor,
          }}
        >
          {user.display_name}
        </div>
        <button onClick={savePersonColor}>Profil speichern</button>
        <form className="password-settings" onSubmit={changePassword}>
          <h2>Passwort ändern</h2>
          <p className="muted">Dabei werden alle anderen angemeldeten Geräte abgemeldet.</p>
          <Field label="Aktuelles Passwort" name="current_password" type="password" />
          <Field label="Neues Passwort (mindestens 12 Zeichen)" name="password" type="password" />
          <Field label="Neues Passwort bestätigen" name="password_confirm" type="password" />
          <button>Passwort ändern</button>
        </form>
      </section>}
      {settingsSection === "calendar" && <section id="settings-calendar" className="themebox settings-card">
        <h2>Meine Kalenderfarben</h2>
        <p className="muted">Diese Farben gelten nur für deine persönliche Kalenderansicht.</p>
        <h3>Schule</h3><div className="themepicker"><input type="color" value={calendarColors.school_color} onChange={(event) => setCalendarColors({...calendarColors, school_color: event.target.value})}/><code>{calendarColors.school_color.toUpperCase()}</code></div>
        <h3>Ferien</h3><div className="themepicker"><input type="color" value={calendarColors.holiday_color} onChange={(event) => setCalendarColors({...calendarColors, holiday_color: event.target.value})}/><code>{calendarColors.holiday_color.toUpperCase()}</code></div>
        {(user.role === "ADMIN" || sectionAccess.birthdays.includes(user.id)) && <><h3>Geburtstage</h3><div className="themepicker"><input type="color" value={calendarColors.birthday_color} onChange={(event) => setCalendarColors({...calendarColors, birthday_color: event.target.value})}/><code>{calendarColors.birthday_color.toUpperCase()}</code></div></>}
        {(user.role === "ADMIN" || sectionAccess.waste_collection.includes(user.id)) && <><h3>Abfallkalender</h3><div className="themepicker"><input type="color" value={calendarColors.waste_color} onChange={(event) => setCalendarColors({...calendarColors, waste_color: event.target.value})}/><code>{calendarColors.waste_color.toUpperCase()}</code></div></>}
        <button onClick={saveCalendarColors}>Kalenderfarben speichern</button>
      </section>}
      {user.role === "ADMIN" && settingsSection === "access" && (
        <SectionAccessSettings people={people} value={sectionAccess} onChange={onSectionAccessChange} />
      )}
      {user.role === "ADMIN" && settingsSection === "sources" && <CalendarSourceOverview />}
      {user.role === "ADMIN" && settingsSection === "updates" && <section id="settings-updates" className="themebox settings-card"><h2>Aktualisierungen</h2><p className="muted">Installiert: Version {updateMeta?.version || "…"}. Die Prüfung kann unabhängig vom automatischen Prüfintervall neu gestartet werden.</p>{updateCheckMessage && <p className={updateMeta?.update_available ? "success" : "hint"}>{updateCheckMessage}</p>}<button type="button" onClick={checkForUpdates} disabled={checkingUpdates}>{checkingUpdates ? "Suche nach Update …" : "Jetzt nach Update suchen"}</button></section>}
      {user.role === "ADMIN" && settingsSection === "integrations" && (
        <IntegrationSettings />
      )}
      {user.role === "ADMIN" && settingsSection === "audit" && <AuditLogSettings people={people} />}
      {user.role === "ADMIN" && settingsSection === "appearance" && (
        <section id="settings-global-theme" className="themebox globaltheme settings-card">
          <h2>Akzentfarbe</h2>
          <p className="muted">
            Die Farbe wird appweit für Navigation, Schaltflächen und
            Hervorhebungen verwendet.
          </p>
          <div className="themepicker">
            <input
              type="color"
              value={color}
              onChange={(e) => preview(e.target.value)}
              aria-label="Akzentfarbe auswählen"
            />
            <code>{color.toUpperCase()}</code>
          </div>
          <div className="themepreview">Vorschau</div>
          <p className="hint">Farben für Schule, Ferien, Geburtstage und Abfall stellst du ausschließlich im Bereich „Kalender“ ein.</p>
          <button onClick={save}>Akzentfarbe speichern</button>
        </section>
      )}
      </div>
    </>
  );
}

function ChangelogModal({ meta, onClose }: { meta: ApplicationMeta; onClose: () => void }) {
  return (
    <div className="modal changelog-modal" role="dialog" aria-modal="true" aria-labelledby="changelog-title">
      <section className="panel">
        <button type="button" className="close" onClick={onClose} aria-label="Schließen">×</button>
        <h2 id="changelog-title">Änderungsprotokoll</h2>
        <div className="changelog-content">
          {meta.changelog.split("\n").map((line, index) =>
            line.startsWith("## ") ? <h3 key={index}>{line.slice(3)}</h3> :
            line.startsWith("### ") ? <h4 key={index}>{line.slice(4)}</h4> :
            line.startsWith("- ") ? <p className="changelog-item" key={index}>{line.slice(2)}</p> :
            line && !line.startsWith("# ") ? <p key={index}>{line}</p> : null
          )}
        </div>
      </section>
    </div>
  );
}

type IntegrationToken = { id: number; name: string; scopes: string[]; last_used_at: string | null; revoked_at: string | null };
type Webhook = { id: number; name: string; url: string; events: string[]; is_active: boolean };
type OutboxEntry = { id:number; channel:"email"|"webhook"; recipient:string; event_type:string; attempts:number; last_error:string|null; delivered_at:string|null; created_at:string };

function IntegrationSettings() {
  const [mail, setMail] = useState({ enabled: false, host: "", port: 587, username: "", password: "", from_address: "FamilienPlan <familienplan@example.de>", app_url: location.origin, security: "starttls", password_configured: false });
  const [tokens, setTokens] = useState<IntegrationToken[]>([]), [tokenName, setTokenName] = useState("Home Assistant"), [newToken, setNewToken] = useState(""), [apiChildren, setApiChildren] = useState<Child[]>([]), [selectedChildren, setSelectedChildren] = useState<number[]>([]), [privateAccess, setPrivateAccess] = useState(false);
  const [hooks, setHooks] = useState<Webhook[]>([]), [hookName, setHookName] = useState("Home Assistant"), [hookUrl, setHookUrl] = useState(""), [newSecret, setNewSecret] = useState("");
  const [outbox, setOutbox] = useState<OutboxEntry[]>([]), [showOutbox, setShowOutbox] = useState(false);
  const [message, setMessage] = useState(""), [error, setError] = useState("");
  const reload = () => Promise.all([
    api<any>("/settings/mail").then((x) => setMail((old) => ({ ...old, ...x, app_url: !x.app_url || x.app_url.includes("localhost") ? location.origin : x.app_url, password: "" }))),
    api<IntegrationToken[]>("/integration-tokens").then(setTokens),
    api<Webhook[]>("/webhooks").then(setHooks),
    api<Child[]>("/children").then((items) => { setApiChildren(items); setSelectedChildren((old) => old.length ? old : items.map((x)=>x.id)); }),
    api<OutboxEntry[]>("/outbox").then(setOutbox),
  ]).catch((x) => setError((x as Error).message));
  useEffect(() => { void reload(); }, []);
  async function saveMail() {
    setError(""); setMessage("");
    try { await api("/settings/mail", { method: "PUT", body: JSON.stringify(mail) }); setMail({ ...mail, password: "", password_configured: mail.password_configured || !!mail.password }); setMessage("Mailserver gespeichert."); }
    catch (x) { setError((x as Error).message); }
  }
  async function createToken() {
    setError("");
    try { const x = await api<{token:string}>("/integration-tokens", { method:"POST", body:JSON.stringify({ name:tokenName, scopes:["read:children","read:stays","read:appointments","read:birthdays","read:holidays",...(privateAccess?["read:private"]:[])], child_ids:selectedChildren }) }); setNewToken(x.token); await reload(); }
    catch (x) { setError((x as Error).message); }
  }
  async function createWebhook() {
    setError("");
    try { const x = await api<{secret:string}>("/webhooks", { method:"POST", body:JSON.stringify({name:hookName,url:hookUrl,events:["*"]}) }); setNewSecret(x.secret); setHookUrl(""); await reload(); }
    catch (x) { setError((x as Error).message); }
  }
  return <section id="settings-integrations" className="themebox integration-settings settings-card settings-wide">
    <h2>Integrationen</h2>
    <p className="muted">REST-API, signierte Webhooks und E-Mail-Benachrichtigungen zentral verwalten. MQTT ist bewusst noch nicht enthalten.</p>
    {error && <p className="error">{error}</p>}{message && <p className="success">{message}</p>}
    <div className="integration-card">
    <div className="integration-card-head"><div><h3>E-Mail-Benachrichtigungen</h3><p className="muted">Informiert eingeladene Personen und Beteiligte automatisch über neue Anfragen und Entscheidungen.</p></div><label className="switch"><input type="checkbox" checked={mail.enabled} onChange={(e)=>setMail({...mail,enabled:e.target.checked})}/><span aria-hidden="true"/><b>{mail.enabled ? "Aktiv" : "Inaktiv"}</b></label></div>
    <div className="integration-grid">
      <label>SMTP-Server<input value={mail.host || ""} onChange={(e)=>setMail({...mail,host:e.target.value})}/></label>
      <label>Port<input type="number" value={mail.port} onChange={(e)=>setMail({...mail,port:Number(e.target.value)})}/></label>
      <label>Benutzername<input value={mail.username || ""} onChange={(e)=>setMail({...mail,username:e.target.value})}/></label>
      <label>Passwort<input type="password" value={mail.password} placeholder={mail.password_configured ? "Gespeichert – leer lassen zum Beibehalten" : ""} onChange={(e)=>setMail({...mail,password:e.target.value})}/></label>
      <label>Absender<input value={mail.from_address} onChange={(e)=>setMail({...mail,from_address:e.target.value})}/></label>
      <label>App-Adresse für Links<input type="url" value={mail.app_url} placeholder={location.origin} onChange={(e)=>setMail({...mail,app_url:e.target.value})}/></label>
      <label>Verbindungssicherheit<select value={mail.security} onChange={(e)=>setMail({...mail,security:e.target.value})}><option value="ssl">SSL/TLS (meist Port 465)</option><option value="starttls">STARTTLS (meist Port 587)</option><option value="none">Unverschlüsselt</option></select></label>
    </div>
    <div className="buttonrow"><button onClick={saveMail}>Mailserver speichern</button><button className="secondary" onClick={async()=>{try{const result=await api<{recipient:string}>("/settings/mail/test",{method:"POST"});setMessage(`Testmail an ${result.recipient} wurde in die Versandwarteschlange gelegt.`);window.setTimeout(()=>void reload(),1200)}catch(x){setError((x as Error).message)}}}>Testmail an {getSessionUser()?.email || "mich"}</button><button className="quiet" onClick={()=>{setShowOutbox(!showOutbox);void reload()}}>{showOutbox?"Warteschlange ausblenden":"Versandstatus anzeigen"}</button></div>
    {showOutbox && <div className="outbox"><header><strong>Letzte Zustellungen</strong><button className="quiet" onClick={()=>void reload()}>Aktualisieren</button></header>{outbox.length===0?<p className="muted">Noch keine Nachrichten vorhanden.</p>:outbox.map((item)=><article key={item.id}><span className={`delivery-state ${item.delivered_at?"sent":item.last_error?"failed":"waiting"}`}>{item.delivered_at?"Versendet":item.last_error?"Fehlgeschlagen":"Wartet"}</span><div><strong>{item.channel==="email"?"E-Mail":"Webhook"} · {item.event_type}</strong><small>An: {item.recipient} · {new Date(item.created_at).toLocaleString("de-DE")}{item.attempts?` · ${item.attempts} Versuche`:""}</small>{item.last_error&&<p className="delivery-error">{item.last_error}</p>}</div></article>)}</div>}
    </div>
    <div className="integration-card">
    <div className="integration-card-head"><div><h3>REST-API-Schlüssel</h3><p className="muted">Für ioBroker, Home Assistant und weitere lokale Integrationen. Kalenderdaten einschließlich Betreuungszeiten: <code>/api/v1/integrations/v1/calendar</code></p></div><span className="integration-badge">Nur Lesen</span></div>
    <p className="muted">Der Schlüssel wird nur einmal vollständig angezeigt. Basis: <code>/api/v1/integrations/v1</code></p>
    <fieldset><legend>Freigegebene Kinder</legend>{apiChildren.map((child)=><label key={child.id} className="checkline"><input type="checkbox" checked={selectedChildren.includes(child.id)} onChange={(e)=>setSelectedChildren(e.target.checked?[...selectedChildren,child.id]:selectedChildren.filter((id)=>id!==child.id))}/>{child.display_name}</label>)}<label className="checkline"><input type="checkbox" checked={privateAccess} onChange={(e)=>setPrivateAccess(e.target.checked)}/>Auch private Termine und Geburtstage freigeben</label></fieldset>
    <div className="buttonrow"><input value={tokenName} onChange={(e)=>setTokenName(e.target.value)} aria-label="Name des API-Schlüssels"/><button onClick={createToken}>API-Schlüssel erstellen</button></div>
    {newToken && <div className="secret-once"><code>{newToken}</code><button onClick={()=>navigator.clipboard.writeText(newToken)}>Kopieren</button></div>}
    {tokens.map((x)=><div className="integration-row" key={x.id}><span><strong>{x.name}</strong><small>{x.revoked_at ? "Widerrufen" : x.last_used_at ? `Zuletzt genutzt: ${new Date(x.last_used_at).toLocaleString("de-DE")}` : "Noch nicht genutzt"}</small></span>{!x.revoked_at&&<button className="danger" onClick={async()=>{await api(`/integration-tokens/${x.id}`,{method:"DELETE"});await reload()}}>Widerrufen</button>}</div>)}
    </div>
    <div className="integration-card">
    <div className="integration-card-head"><div><h3>Webhooks</h3><p className="muted">Ereignisse in Echtzeit an externe Systeme senden.</p></div><span className="integration-badge">Signiert</span></div>
    <p className="muted">POST-Nachrichten sind mit <code>X-FamilienPlan-Signature</code> (HMAC-SHA256) signiert und werden bei Fehlern erneut versucht.</p>
    <div className="integration-grid"><label>Name<input value={hookName} onChange={(e)=>setHookName(e.target.value)}/></label><label>Empfänger-URL<input type="url" placeholder="http://homeassistant:8123/api/webhook/…" value={hookUrl} onChange={(e)=>setHookUrl(e.target.value)}/></label></div>
    <button onClick={createWebhook}>Webhook hinzufügen</button>
    {newSecret && <div className="secret-once"><span>Signatur-Schlüssel: </span><code>{newSecret}</code><button onClick={()=>navigator.clipboard.writeText(newSecret)}>Kopieren</button></div>}
    {hooks.map((x)=><div className="integration-row" key={x.id}><span><strong>{x.name}</strong><small>{x.url}</small></span><div className="buttonrow"><button className="secondary" onClick={()=>api(`/webhooks/${x.id}/test`,{method:"POST"}).then(()=>setMessage("Test-Webhook eingeplant."))}>Test</button><button className="danger" onClick={async()=>{await api(`/webhooks/${x.id}`,{method:"DELETE"});await reload()}}>Löschen</button></div></div>)}
    </div>
  </section>;
}

class AppErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("FamilienPlan konnte nicht dargestellt werden", error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <main className="auth">
        <section className="panel">
          <h2>Die Seite konnte nicht angezeigt werden</h2>
          <p className="error">{this.state.error.message}</p>
          <button onClick={() => location.reload()}>Erneut laden</button>
        </section>
      </main>
    );
  }
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppErrorBoundary>
      {location.pathname.startsWith("/invite/") ? <InviteAccept /> : location.pathname.startsWith("/reset-password/") ? <ResetPassword /> : <App />}
    </AppErrorBoundary>
  </React.StrictMode>,
);

document.addEventListener("click", (event) => {
  const button = (event.target as HTMLElement).closest("button");
  if (!button || button.disabled) return;
  button.classList.remove("button-clicked");
  void button.offsetWidth;
  button.classList.add("button-clicked");
  window.setTimeout(() => button.classList.remove("button-clicked"), 450);
});
