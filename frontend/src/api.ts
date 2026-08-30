export type User = {
  id: number;
  username: string;
  display_name: string;
  first_name: string | null;
  last_name: string | null;
  email: string;
  role: "VIEWER" | "EDITOR" | "ADMIN";
  color: string;
  birth_date: string | null;
  allowed_event_types: EventType[];
  is_pending: boolean;
};
export type EventType = "STAY" | "BIRTHDAY" | "GENERAL" | "SCHOOL" | "CLEANING" | "WASTE" | "OTHER";
export type Child = {
  id: number;
  first_name: string;
  last_name: string;
  display_name: string;
  birth_date: string | null;
  school: string | null;
  school_city: string | null;
  school_address: string | null;
  school_state_code: string | null;
  school_url: string | null;
  school_calendar_url: string | null;
  school_class: string | null;
  care: string | null;
  care_city: string | null;
  care_url: string | null;
  care_calendar_url: string | null;
  default_responsible_user_id: number | null;
  notes: string | null;
  is_active: boolean;
};
export type Institution = {
  name: string;
  city: string | null;
  address: string | null;
  state_code: string | null;
  website: string | null;
  calendar_url: string | null;
};
export type CalendarEvent = {
  id: number;
  title: string;
  description: string | null;
  starts_at: string;
  ends_at: string;
  all_day: boolean;
  category: string;
  child_id: number | null;
  source_id: number | null;
  raw_data: { waste_type?: string; [key: string]: unknown } | null;
  created_by_id: number | null;
  color: string | null;
  is_private: boolean;
  event_type: EventType;
  custom_type_label: string | null;
  visible_to_user_ids: number[] | null;
  recurrence_group: string | null;
  recurrence_frequency: "WEEKLY" | "MONTHLY" | null;
  recurrence_interval: number | null;
  recurrence_until: string | null;
};
export type Stay = {
  id: number;
  child_id: number;
  responsible_user_id: number;
  responsible_display_name: string | null;
  starts_at: string;
  ends_at: string;
  status: string;
  note: string | null;
  recurrence_rule_id: number | null;
  recurrence_interval_weeks: number | null;
  recurrence_frequency: "WEEKLY" | "MONTHLY";
  recurrence_day_of_month: number | null;
  recurrence_until: string | null;
};
export type Holiday = { name: string; starts_on: string; ends_on: string };
export type ChangeRequest = {
  id: number;
  object_type: string;
  object_id: number;
  requested_by_id: number;
  requested_by_name: string;
  affected_user_id: number;
  affected_user_name: string;
  status: "PROPOSED" | "CHANGE_PROPOSED";
  proposed_data: {
    action?: "DELETE" | "CREATE" | "GROUP_CREATE";
    title?: string;
    items?: Array<{
      stay_id: number;
      child_id: number;
      responsible_user_id: number;
      starts_at: string;
      ends_at: string;
      name: string;
      kind: string;
      comment?: string | null;
    }>;
    starts_at?: string;
    ends_at?: string;
    responsible_user_id?: number;
    note?: string | null;
    scope: "occurrence" | "future" | "series";
    recurrence_interval_weeks?: number | null;
    recurrence_until?: string | null;
  };
  before_data: {
    starts_at?: string;
    ends_at?: string;
    responsible_user_id?: number;
    note?: string | null;
  };
  child_id: number | null;
  child_name: string | null;
  created_at: string;
};
export type PersonAccess = {
  user: User;
  child_permissions: Record<string, "VIEW" | "EDIT">;
};
export type AppNotification = {
  id: number;
  kind: string;
  title: string;
  body: string;
  read_at: string | null;
  created_at: string;
};
export type SearchResult = {
  kind: "child" | "person" | "event" | "stay" | "birthday";
  id: number;
  title: string;
  subtitle: string;
  starts_at: string | null;
};
export type Birthday = {
  id: number;
  first_name: string;
  last_name: string;
  display_name: string;
  birth_date: string;
  is_private: boolean;
  visible_to_user_ids: number[] | null;
  event_type: "BIRTHDAY";
  created_by_id: number;
};
let csrf = "";
let sessionUser: User | null = null;
let pendingRequests = 0;
function requestStarted() {
  pendingRequests += 1;
  document.documentElement.classList.add("api-pending");
}
function requestFinished() {
  pendingRequests = Math.max(0, pendingRequests - 1);
  if (!pendingRequests) document.documentElement.classList.remove("api-pending");
}
export function setCsrf(value: string) {
  csrf = value;
}
export function getSessionUser() {
  return sessionUser;
}

type ValidationIssue = {
  loc?: Array<string | number>;
  msg?: string;
  type?: string;
  ctx?: { min_length?: number };
};
function errorMessage(data: unknown): string {
  const detail = (data as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const labels: Record<string, string> = {
      email: "E-Mail-Adresse",
      username: "Benutzername",
      display_name: "Anzeigename",
      first_name: "Vorname",
      last_name: "Nachname",
      password: "Passwort",
      password_confirm: "Passwortbestätigung",
      token: "Einladungslink",
    };
    return (detail as ValidationIssue[])
      .map((issue) => {
        const field = String(issue.loc?.at(-1) || "Eingabe"),
          label = labels[field] || field;
        if (issue.type === "missing") return `${label}: Bitte ausfüllen.`;
        if (issue.type === "string_too_short")
          return `${label}: mindestens ${issue.ctx?.min_length || ""} Zeichen erforderlich.`;
        if (issue.type === "value_error")
          return (issue.msg || "Ungültige Eingabe").replace(
            /^Value error,\s*/,
            "",
          );
        return `${label}: ${issue.msg || "ungültige Eingabe"}`;
      })
      .join(" ");
  }
  return "Die Anfrage konnte nicht verarbeitet werden. Bitte prüfe die Eingaben und versuche es erneut.";
}
type ApiOptions = RequestInit & { background?: boolean };

export async function api<T>(
  path: string,
  options: ApiOptions = {},
): Promise<T> {
  const background = options.background === true;
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (options.method && !["GET", "HEAD"].includes(options.method) && csrf)
    headers.set("X-CSRF-Token", csrf);
  if (!background) requestStarted();
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      ...options,
      headers,
      credentials: "include",
    });
    if (
      response.status === 403 &&
      path !== "/auth/me" &&
      options.method &&
      !["GET", "HEAD"].includes(options.method)
    ) {
      const failed = await response.clone().json().catch(() => ({}));
      if (failed?.detail === "Ungültiger CSRF-Schutz") {
        const session = await fetch("/api/v1/auth/me", {
          credentials: "include",
        });
        if (session.ok) {
          const current = await session.json();
          if (current?.csrf_token) {
            csrf = current.csrf_token;
            sessionUser = current.user || sessionUser;
            headers.set("X-CSRF-Token", csrf);
            response = await fetch(`/api/v1${path}`, {
              ...options,
              headers,
              credentials: "include",
            });
          }
        }
      }
    }
  } finally {
    if (!background) requestFinished();
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(errorMessage(data));
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json();
  if (
    (path === "/auth/me" ||
      path === "/auth/login" ||
      path === "/setup/admin") &&
    data?.user
  )
    sessionUser = data.user;
  if (
    /^\/children(?:\/\d+)?$/.test(path) &&
    ["POST", "PUT"].includes(options.method || "GET") &&
    data?.school_calendar_url
  ) {
    fetch(`/api/v1/children/${data.id}/calendar/sync`, {
      method: "POST",
      headers: { "X-CSRF-Token": csrf },
      credentials: "include",
    }).catch(() => {});
  }
  return data as T;
}
