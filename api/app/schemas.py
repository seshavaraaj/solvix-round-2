"""Pydantic models that mirror contract §5 one-to-one (plan B3.7).
Field names must match the contract exactly; do not rename without a
`contract/` PR."""
from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

Confidence = Literal["high", "medium", "low"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LineString(_M):
    type: Literal["LineString"] = "LineString"
    coordinates: list[list[float]]


class RouteStop(_M):
    id: str
    name: str
    lat: float
    lon: float
    seq: int


class Route(_M):
    id: str
    name: str
    depot_id: str
    color: str
    min_headway_min: float
    shape: LineString
    stops: list[RouteStop]


class Bus(_M):
    id: str
    route_id: str
    direction: int
    lat: float
    lon: float
    bearing: float
    load_factor: float
    delay_min: float
    dark: bool
    last_seen: str


class FlagState(_M):
    on: bool
    confidence: Confidence
    evidence: Optional[str]


class RouteFlags(_M):
    overcrowded: FlagState
    underused: FlagState
    delay_emerging: FlagState
    bunching: FlagState


class RouteHealth(_M):
    route_id: str
    direction: int
    flags: RouteFlags


class FeedHealth(_M):
    buses_expected: int
    buses_reporting: int
    share_reporting: float
    mode: Literal["replay", "live"]
    fresh: bool


class Effect(_M):
    wait_min_before: float
    wait_min_after: float
    peak_load_before: float
    peak_load_after: float


class ExpectedEffect(_M):
    to_route: Optional[Effect]
    from_route: Optional[Effect]


class Recommendation(_M):
    id: str
    created_at: str
    action: Literal["move_bus", "add_trip", "release_bus"]
    from_route_id: Optional[str]
    to_route_id: Optional[str]
    bus_count: int
    window_start: str
    window_end: str
    trigger_flags: list[str]
    expected_effect: ExpectedEffect
    deadhead_km: float
    confidence: Confidence
    explanation: str
    status: Literal["pending", "approved", "rejected", "expired"]
    solver: Literal["cp_sat", "greedy"]


RejectReason = Literal["no_driver", "bus_unavailable", "local_knowledge", "forecast_wrong", "other"]


class DecisionIn(_M):
    recommendation_id: str
    decision: Literal["approve", "reject"]
    reason: Optional[RejectReason] = None
    note: Optional[str] = Field(default=None, max_length=500)


class Decision(_M):
    recommendation_id: str
    decision: Literal["approve", "reject"]
    reason: Optional[RejectReason]
    note: Optional[str]
    decided_by: str
    decided_at: str


class SimMetrics(_M):
    avg_wait_min: float
    p95_wait_min: float
    left_behind: int
    overload_min: int
    bunching_events: int


class SeriesPoint(_M):
    t: str
    load_without: float
    load_with: float


class WhatIfIn(_M):
    recommendation_id: str


class WhatIfResult(_M):
    recommendation_id: str
    horizon_min: int
    runtime_s: float
    without: SimMetrics
    with_: SimMetrics = Field(alias="with", serialization_alias="with")
    series: list[SeriesPoint]

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ScenarioRow(_M):
    scenario: str
    strategy: str
    error_level: Union[float, str]
    avg_wait_min: float
    p95_wait_min: float
    left_behind: int
    overload_min: int
    bunching_events: int
    avg_load_factor: float
    deadhead_km: float
    changes_per_hour: float


class ScenarioResult(_M):
    scenarios: list[str]
    strategies: list[str]
    error_levels: list[Union[float, str]]
    rows: list[ScenarioRow]


class Alert(_M):
    id: str
    route_id: str
    kind: Literal["delay", "bunching", "crowded", "service_change"]
    message: str
    since: str


class CrowdingReport(_M):
    bus_id: str
    route_id: str
    level: Literal["crowded", "ok", "empty"]
    lat: Optional[float] = None
    lon: Optional[float] = None


class FleetConfig(_M):
    depot_id: str
    name: str
    lat: float
    lon: float
    fleet_size: int = Field(ge=0)
    reserve: int = Field(ge=0)
    out_of_service: int = Field(ge=0)


class LoginIn(_M):
    username: str
    password: str


class DeviceIn(_M):
    device_id: str = Field(min_length=8, max_length=64)


class TokenOut(_M):
    token: str
    role: Literal["operator", "admin", "rider"]
    expires_at: str


class ClockOut(_M):
    t: str
    speed: Literal[1, 10, 30]
    playing: bool
    scenario: str


class ClockIn(_M):
    action: Literal["play", "pause", "jump"]
    speed: Optional[Literal[1, 10, 30]] = None
    scenario: Optional[str] = None
    t: Optional[str] = None


class StateOut(_M):
    t: str
    buses: list[Bus]
    route_health: list[RouteHealth]
    feed: FeedHealth


class EtaOut(_M):
    bus_id: str
    route_id: str
    eta_min: float
    load_factor: float


class CycleOut(_M):
    t: str
    ran: bool
    recommendations: list[Recommendation]


class HealthOut(_M):
    status: Literal["ok", "loading", "error"]
    models_loaded: bool
    db: Literal["ok", "down"]
    version: str
    error: Optional[str] = None
