"""Deterministic synthetic interventions on copies of hourly readings only."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ecoproof.detect.classifier import HOUR, Key, Readings, Weather, utc_hour
from ecoproof.graph.geo import Coordinate, haversine_km, wind_alignment, wind_vector
from ecoproof.transform.validation import number


FaultKind = Literal["stuck", "zero", "spike", "drift", "degradation"]
FAULT_KINDS = ("stuck", "zero", "spike", "drift", "degradation")


@dataclass(frozen=True)
class Change:
    station_id: str
    ts: datetime
    original: float
    injected: float
    role: str


@dataclass(frozen=True)
class Injection:
    kind: str
    readings: dict[Key, float]
    changes: tuple[Change, ...]
    fault_keys: frozenset[Key]
    parameters: dict[str, object]


def _hours(value: int) -> int:
    if type(value) is not int or value < 1:
        raise ValueError("hours must be a positive integer")
    return value


def _change(readings: Readings, key: Key, value: float, role: str) -> Change:
    if key not in readings:
        raise ValueError(f"Missing observation for injection: {key}")
    original = number(readings[key], "original PM2.5", 0, 1500)
    injected = number(value, "injected PM2.5", 0, 1500)
    return Change(key[0], key[1], original, injected, role)


def _result(kind: str, readings: Readings, changes: list[Change], parameters: dict) -> Injection:
    if not any(change.original != change.injected for change in changes):
        raise ValueError("Injection has no observable effect")
    result = dict(readings)
    for change in changes:
        result[change.station_id, change.ts] = change.injected
    # Every intervention hour is labeled, even if a stuck value happens to equal
    # one original sample. Dropping those harder cases would inflate recall.
    faults = frozenset((change.station_id, change.ts) for change in changes if change.role == "fault")
    return Injection(kind, result, tuple(changes), faults, parameters)


def inject_fault(
    readings: Readings, *, kind: FaultKind, station_id: str, start: datetime,
    hours: int, spike_delta: float = 100.0, drift_delta: float = 30.0,
    degradation_factor: float = 0.7,
) -> Injection:
    """Inject a whole observed window without clipping, filling gaps, or mutation.

    Stuck uses the last pre-window value; drift adds offsets growing to drift_delta.
    Degradation multiplies every window sample by the specified 0.6–0.8 factor.
    """
    if kind not in FAULT_KINDS:
        raise ValueError("Unknown fault kind")
    start, hours = utc_hour(start), _hours(hours)
    spike_delta = number(spike_delta, "spike_delta", 0)
    drift_delta = number(drift_delta, "drift_delta", 0)
    degradation_factor = number(degradation_factor, "degradation_factor", 0.6, 0.8)
    keys = [(station_id, start + step * HOUR) for step in range(hours)]
    if any(key not in readings for key in keys):
        raise ValueError("Injection window has missing readings")
    stuck = None
    if kind == "stuck":
        if (station_id, start - HOUR) not in readings:
            raise ValueError("Stuck injection needs the preceding observation")
        stuck = number(readings[station_id, start - HOUR], "stuck value", 0, 1500)
    changes = []
    for step, key in enumerate(keys):
        original = number(readings[key], "original PM2.5", 0, 1500)
        value = {"stuck": stuck, "zero": 0.0, "spike": original + spike_delta,
                 "drift": original + drift_delta * (step + 1) / hours,
                 "degradation": original * degradation_factor}[kind]
        changes.append(_change(readings, key, value, "fault"))
    parameters = {"station_id": station_id, "start": start.isoformat(), "hours": hours}
    parameters.update({"stuck": {"constant": stuck}, "zero": {"constant": 0.0},
                       "spike": {"delta": spike_delta}, "drift": {"final_delta": drift_delta},
                       "degradation": {"factor": degradation_factor}}[kind])
    return _result(kind, readings, changes, parameters)


def inject_plume(
    readings: Readings, stations: Mapping[str, Coordinate], weather: Weather, *,
    station_id: str, start: datetime, amplitude: float = 100.0, decay: float = 0.5,
    tau_km: float = 20.0, lag_tolerance_hours: float = 1.0, max_neighbors: int = 2,
) -> Injection:
    """Add a source spike and smaller delayed rises to observed downwind neighbors.

    This is a synthetic plume-shaped negative control, not a measured real plume.
    Recipients are chosen by geometry/availability, never detector predictions.
    """
    start = utc_hour(start)
    amplitude = number(amplitude, "amplitude", 0)
    decay = number(decay, "decay", 0, 1)
    tau_km = number(tau_km, "tau_km", 0)
    lag_tolerance_hours = number(lag_tolerance_hours, "lag_tolerance_hours", 0)
    if amplitude == 0 or not 0 < decay < 1:
        raise ValueError("Plume needs positive amplitude and a strictly smaller neighbor rise")
    _hours(max_neighbors)
    if station_id not in stations or (station_id, start) not in readings or start not in weather:
        raise ValueError("Plume needs a source station, observation, and wind")
    speed, direction = weather[start]
    wind_vector(speed, direction)
    if speed == 0:
        raise ValueError("Plume transport requires nonzero wind")
    source = _change(readings, (station_id, start), readings[station_id, start] + amplitude, "plume_source")
    candidates = []
    for neighbor in sorted(stations):
        if neighbor == station_id:
            continue
        distance = haversine_km(stations[station_id], stations[neighbor])
        alignment = wind_alignment(stations[station_id], stations[neighbor], direction_from_deg=direction)
        if distance > tau_km or alignment <= 1e-12:
            continue
        travel = distance / (speed * 3.6)
        lags = [lag for lag in (1, 2, 3) if abs(lag - travel) <= lag_tolerance_hours]
        if not lags:
            continue
        lag = min(lags, key=lambda item: (abs(item - travel), item))
        key = (neighbor, start + lag * HOUR)
        if key not in readings:
            continue
        change = _change(readings, key, readings[key] + amplitude * decay, "plume_arrival")
        candidates.append((-alignment, distance, neighbor, lag, travel, change))
    if not candidates:
        raise ValueError("No observed downwind recipient within the 1–3 hour transport window")
    chosen = sorted(candidates, key=lambda item: item[:3])[:max_neighbors]
    parameters = {"station_id": station_id, "start": start.isoformat(), "amplitude": amplitude,
                  "decay": decay, "tau_km": tau_km, "lag_tolerance_hours": lag_tolerance_hours,
                  "recipients": [{"station_id": row[2], "lag_hours": row[3], "travel_hours": row[4],
                                  "alignment": -row[0]} for row in chosen]}
    return _result("plume", readings, [source] + [row[5] for row in chosen], parameters)
