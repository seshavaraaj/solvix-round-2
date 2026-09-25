// Mirrors .reports/implementation/00-shared-contract.md §5–§6.
// Do not rename or reshape fields here. Change the contract first (contract §10).
// admin/src/api/types.ts must stay identical to this file.

export type IsoTime = string;
export type Confidence = "high" | "medium" | "low";
export type Role = "operator" | "admin" | "rider";

export interface Stop {
  id: string;
  name: string;
  lat: number;
  lon: number;
  seq: number;
}

export interface LineString {
  type: "LineString";
  coordinates: [number, number][];
}

export interface Route {
  id: string;
  name: string;
  depot_id: string;
  color: string;
  min_headway_min: number;
  shape: LineString;
  stops: Stop[];
}

export interface Bus {
  id: string;
  route_id: string;
  direction: number;
  lat: number;
  lon: number;
  bearing: number;
  load_factor: number;
  delay_min: number;
  dark: boolean;
  last_seen: IsoTime;
}

export interface Flag {
  on: boolean;
  confidence: Confidence;
  evidence: string | null;
}

export type FlagName = "overcrowded" | "underused" | "delay_emerging" | "bunching";
export const FLAG_NAMES: FlagName[] = ["overcrowded", "underused", "delay_emerging", "bunching"];

export interface RouteHealth {
  route_id: string;
  direction: number;
  flags: Record<FlagName, Flag>;
}

export interface FeedHealth {
  buses_expected: number;
  buses_reporting: number;
  share_reporting: number;
  mode: "replay" | "live";
  fresh: boolean;
}

export interface Health {
  status: "ok" | "loading";
  models_loaded: boolean;
  db: "ok" | "down";
  version: string;
}

export interface LoginResponse {
  token: string;
  role: Role;
  expires_at: IsoTime | number;
}

export type Speed = 1 | 10 | 30;
export type Scenario = "normal_weekday" | "heavy_rain" | "event_surge" | "breakdown";
export const SCENARIOS: Scenario[] = ["normal_weekday", "heavy_rain", "event_surge", "breakdown"];

export interface Clock {
  t: IsoTime;
  speed: Speed;
  playing: boolean;
  scenario: Scenario;
}

export interface ClockCommand {
  action: "play" | "pause" | "jump";
  speed?: Speed;
  scenario?: Scenario;
  t?: IsoTime;
}

export interface StateResponse {
  t: IsoTime;
  buses: Bus[];
  route_health: RouteHealth[];
  feed: FeedHealth;
}

export interface Eta {
  bus_id: string;
  route_id: string;
  eta_min: number;
  load_factor: number;
}

export interface RouteEffect {
  wait_min_before: number;
  wait_min_after: number;
  peak_load_before: number;
  peak_load_after: number;
}

export type RecommendationAction = "move_bus" | "add_trip" | "release_bus";
export type RecommendationStatus = "pending" | "approved" | "rejected" | "expired";

export interface Recommendation {
  id: string;
  created_at: IsoTime;
  action: RecommendationAction;
  from_route_id: string | null;
  to_route_id: string | null;
  bus_count: number;
  window_start: IsoTime;
  window_end: IsoTime;
  trigger_flags: FlagName[];
  expected_effect: { to_route?: RouteEffect; from_route?: RouteEffect };
  deadhead_km: number;
  confidence: Confidence;
  explanation: string;
  status: RecommendationStatus;
  solver: "cp_sat" | "greedy";
}

export interface CycleResponse {
  t: IsoTime;
  ran: boolean;
  recommendations: Recommendation[];
}

export type RejectReason =
  | "no_driver"
  | "bus_unavailable"
  | "local_knowledge"
  | "forecast_wrong"
  | "other";
export const REJECT_REASONS: RejectReason[] = [
  "no_driver",
  "bus_unavailable",
  "local_knowledge",
  "forecast_wrong",
  "other",
];

export interface DecisionRequest {
  recommendation_id: string;
  decision: "approve" | "reject";
  reason?: RejectReason;
  note?: string;
}

export interface Decision extends DecisionRequest {
  decided_by: string;
  decided_at: IsoTime;
}

export interface WhatIfMetrics {
  avg_wait_min: number;
  p95_wait_min: number;
  left_behind: number;
  overload_min: number;
  bunching_events: number;
}

export interface WhatIfResult {
  recommendation_id: string;
  horizon_min: number;
  runtime_s: number;
  without: WhatIfMetrics;
  with: WhatIfMetrics;
  series: { t: IsoTime; load_without: number; load_with: number }[];
}

export type ErrorLevel = number | "missed_surge";

export interface ScenarioRow {
  scenario: string;
  strategy: string;
  error_level: ErrorLevel;
  avg_wait_min: number;
  p95_wait_min: number;
  left_behind: number;
  overload_min: number;
  bunching_events: number;
  avg_load_factor: number;
  deadhead_km: number;
  changes_per_hour: number;
}

export interface ScenarioResult {
  scenarios: string[];
  strategies: string[];
  error_levels: ErrorLevel[];
  rows: ScenarioRow[];
}

export interface Alert {
  id: string;
  route_id: string;
  kind: "delay" | "bunching" | "crowded" | "service_change";
  message: string;
  since: IsoTime;
}

export interface FleetConfig {
  depot_id: string;
  name: string;
  lat: number;
  lon: number;
  fleet_size: number;
  reserve: number;
  out_of_service: number;
}
