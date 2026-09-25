// Fetch wrapper for the TransitPulse API (contract §3–§6).
// admin/src/api/client.ts must stay identical to this file.

import type {
  Clock,
  ClockCommand,
  CycleResponse,
  Decision,
  DecisionRequest,
  FleetConfig,
  Health,
  LoginResponse,
  Recommendation,
  RecommendationStatus,
  Route,
  ScenarioResult,
  StateResponse,
  WhatIfResult,
} from "./types";

export const API_URL: string = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

const TOKEN_KEY = "tp_token";
const ROLE_KEY = "tp_role";

export const session = {
  get token(): string | null {
    return sessionStorage.getItem(TOKEN_KEY);
  },
  get role(): string | null {
    return sessionStorage.getItem(ROLE_KEY);
  },
  set(token: string, role: string) {
    sessionStorage.setItem(TOKEN_KEY, token);
    sessionStorage.setItem(ROLE_KEY, role);
  },
  clear() {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(ROLE_KEY);
  },
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Events the UI reacts to globally: server waking up (503 loading) and lost auth (401). */
export type ApiEvent = "waking" | "unauthorized";
type Listener = (e: ApiEvent) => void;
const listeners = new Set<Listener>();

export function onApiEvent(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function emit(e: ApiEvent) {
  listeners.forEach((fn) => fn(e));
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | undefined | null>;
  signal?: AbortSignal;
  /** Return the raw Response instead of parsed JSON (CSV download). */
  raw?: boolean;
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const url = new URL(API_URL + path);
  for (const [k, v] of Object.entries(opts.query ?? {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const token = session.token;
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(url, {
      method: opts.method ?? "GET",
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    // Network failure: a sleeping Render service often refuses or times out before it answers.
    emit("waking");
    throw new ApiError(0, "network", "Cannot reach the server");
  }

  if (!res.ok) {
    let code = "http_" + res.status;
    let message = res.statusText || "Request failed";
    try {
      const body = await res.json();
      if (body?.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
      }
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 503) emit("waking");
    if (res.status === 401) {
      session.clear();
      emit("unauthorized");
    }
    throw new ApiError(res.status, code, message);
  }

  if (opts.raw) return res as unknown as T;
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Health is checked without emitting events so the wake-up screen can poll it freely. */
export async function getHealth(signal?: AbortSignal): Promise<Health | null> {
  try {
    const res = await fetch(API_URL + "/health", { signal });
    if (!res.ok) return null;
    return (await res.json()) as Health;
  } catch {
    return null;
  }
}

export const api = {
  login: (username: string, password: string) =>
    request<LoginResponse>("/auth/login", { method: "POST", body: { username, password } }),

  getClock: () => request<Clock>("/clock"),
  setClock: (cmd: ClockCommand) => request<Clock>("/clock", { method: "POST", body: cmd }),

  getState: (t?: string) => request<StateResponse>("/state", { query: { t } }),
  getRoutes: () => request<Route[]>("/routes"),

  runCycle: (t: string) => request<CycleResponse>("/cycle", { method: "POST", query: { t } }),
  getRecommendations: (status?: RecommendationStatus) =>
    request<Recommendation[]>("/recommendations", { query: { status } }),

  decide: (d: DecisionRequest) => request<Decision>("/decisions", { method: "POST", body: d }),
  getDecisions: (limit: number, offset: number) =>
    request<Decision[]>("/decisions", { query: { limit, offset } }),

  whatIf: (recommendation_id: string, signal?: AbortSignal) =>
    request<WhatIfResult>("/whatif", { method: "POST", body: { recommendation_id }, signal }),
  getResults: () => request<ScenarioResult>("/results"),

  getAdminRoutes: () => request<Route[]>("/admin/routes"),
  putAdminRoute: (r: Route) =>
    request<Route>(`/admin/routes/${encodeURIComponent(r.id)}`, { method: "PUT", body: r }),
  getFleet: () => request<FleetConfig[]>("/admin/fleet"),
  putFleet: (f: FleetConfig) =>
    request<FleetConfig>(`/admin/fleet/${encodeURIComponent(f.depot_id)}`, { method: "PUT", body: f }),
};

/** GET /decisions.csv with the bearer token, then save it as a file. */
export async function downloadDecisionsCsv(): Promise<void> {
  const res = await request<Response>("/decisions.csv", { raw: true });
  const blob = await res.blob();
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = `decisions-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(href);
}
