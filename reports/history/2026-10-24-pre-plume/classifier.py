"""Offline hourly classification per SPEC section 5; labels express evidence.

Baseline fitting uses only an explicit earlier window. Plume decisions may use
up to three hours of later readings: this is retrospective, not a live alarm.
All public datetime inputs must be aware and on a UTC hour boundary.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import math
from statistics import fmean, median
from typing import Literal

from ecoproof.graph.geo import (
    Coordinate, adjacency_matrix, haversine_km, wind_alignment, wind_vector, wind_weights,
)


Label = Literal["VALID", "SENSOR_FAULT_DRIFT", "VERIFIED_PLUME_EVENT"]
Key = tuple[str, datetime]
Readings = Mapping[Key, float]
Weather = Mapping[datetime, tuple[float, float]]
HOUR = timedelta(hours=1)


@dataclass(frozen=True)
class DetectorConfig:
    sigma_km: float
    alpha: float
    tau_km: float = 20.0
    z_threshold: float = 2.5
    scale_floor: float = 1.0  # µg/m³, explicit provisional noise floor.
    min_baseline_samples: int = 24
    recent_hours: int = 6
    persistence_hours: int = 5
    flat_tolerance: float = 0.0
    lag_tolerance_hours: float = 1.0  # Allow hourly sampling around d / speed.

    def __post_init__(self) -> None:
        wind_weights([], sigma_km=self.sigma_km, tau_km=self.tau_km,
                     alpha=self.alpha, speed_m_s=0.0, direction_from_deg=0.0)
        for name in ("z_threshold", "scale_floor"):
            if _number(getattr(self, name), name) <= 0:
                raise ValueError(f"{name} must be positive")
        for name in ("flat_tolerance", "lag_tolerance_hours"):
            if _number(getattr(self, name), name) < 0:
                raise ValueError(f"{name} must be nonnegative")
        for name in ("min_baseline_samples", "recent_hours", "persistence_hours"):
            value = getattr(self, name)
            if type(value) is not int or value < 3:
                raise ValueError(f"{name} must be an integer of at least 3")


@dataclass(frozen=True)
class Baseline:
    sample_count: int
    sigma: float | None
    value_median: float | None
    value_mad: float | None


@dataclass(frozen=True)
class PlumeEvidence:
    station_id: str
    ts: datetime
    lag_hours: int
    travel_hours: float
    alignment: float
    rise: float
    reference: float


@dataclass(frozen=True)
class Classification:
    station_id: str
    ts: datetime
    value: float
    expected: float | None
    residual: float | None
    z: float | None
    label: Label
    neighbor_count: int
    wind_speed: float | None
    wind_dir_deg: float | None
    low_confidence: bool
    reason: str
    baseline_sigma: float | None
    smoothed_z: float | None
    plume_evidence: tuple[PlumeEvidence, ...] = ()
    plume_sources: tuple[Key, ...] = ()


@dataclass(frozen=True)
class DetectionRun:
    records: tuple[Classification, ...]
    baselines: dict[str, Baseline]


@dataclass(frozen=True)
class _Score:
    expected: float | None
    residual: float | None
    neighbors: tuple[str, ...]


def _number(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{name} must be finite")
    try:
        result = float(value)
    except OverflowError:
        raise ValueError(f"{name} must be finite") from None
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def utc_hour(ts: datetime) -> datetime:
    if not isinstance(ts, datetime) or ts.utcoffset() is None:
        raise ValueError("Timestamps must include a timezone")
    ts = ts.astimezone(timezone.utc)
    if ts.minute or ts.second or ts.microsecond:
        raise ValueError("Classifier timestamps must be on UTC hour boundaries")
    return ts


def expected_value(values: Sequence[float | None], weights: Sequence[float]) -> tuple[float | None, int]:
    """Weighted mean and usable count, renormalized after excluding missing values.

    A zero reading is usable. Zero-weight entries (including self-edges) are not.
    Invalid supplied values raise instead of silently becoming missing data.
    """
    if len(values) != len(weights):
        raise ValueError("values and weights must have the same length")
    usable = []
    for value, weight in zip(values, weights):
        weight = _number(weight, "weight")
        if weight < 0:
            raise ValueError("weights must be nonnegative")
        if value is not None:
            value = _number(value, "PM2.5")
            if not 0 <= value <= 1500:
                raise ValueError("PM2.5 must be between 0 and 1500")
            if weight > 0:
                usable.append((value, weight))
    if not usable:
        return None, 0
    largest = max(weight for _, weight in usable)
    total = math.fsum(weight / largest for _, weight in usable)
    mean = math.fsum(value * (weight / largest / total) for value, weight in usable)
    return mean, len(usable)


def robust_sigma(residuals: Sequence[float], *, min_samples: int = 24, floor: float = 1.0) -> float | None:
    """1.4826 * MAD about the median, with a positive noise floor; None if sparse."""
    if type(min_samples) is not int or min_samples < 3:
        raise ValueError("min_samples must be an integer of at least 3")
    if _number(floor, "floor") <= 0:
        raise ValueError("floor must be positive")
    values = [_number(value, "residual") for value in residuals]
    if len(values) < min_samples:
        return None
    center = median(values)
    scale = 1.4826 * median(abs(value - center) for value in values)
    if not math.isfinite(scale):
        raise ValueError("Residual scale overflow")
    return max(floor, scale)


def _inputs(
    stations: Mapping[str, Coordinate], readings: Readings, weather: Weather,
) -> tuple[dict[Key, float], dict[datetime, tuple[float, float]]]:
    if any(not isinstance(station, str) or not station.strip() for station in stations):
        raise ValueError("Station IDs must be nonempty strings")
    normalized = {}
    for (station, ts), raw in readings.items():
        if station not in stations:
            raise ValueError(f"Unknown station: {station}")
        value = _number(raw, "PM2.5")
        if not 0 <= value <= 1500:
            raise ValueError("PM2.5 must be between 0 and 1500")
        normalized[station, utc_hour(ts)] = value
    winds = {}
    for ts, (speed, direction) in weather.items():
        wind_vector(speed, direction)  # Validate supplied weather; absence is allowed.
        winds[utc_hour(ts)] = (float(speed), float(direction) % 360)
    return normalized, winds


def _score_hours(
    stations: Mapping[str, Coordinate], readings: Readings, weather: Weather, config: DetectorConfig,
) -> dict[Key, _Score]:
    ids = sorted(stations)
    coordinates = [stations[station] for station in ids]
    # Validate geometry even for empty input or entirely missing weather.
    adjacency_matrix(coordinates, sigma_km=config.sigma_km, tau_km=config.tau_km)
    scores = {}
    matrices = {}
    for ts in sorted({key[1] for key in readings}):
        values = [readings.get((station, ts)) for station in ids]
        wind = weather.get(ts)
        if wind is not None and wind not in matrices:
            matrices[wind] = wind_weights(coordinates, sigma_km=config.sigma_km,
                                         tau_km=config.tau_km, alpha=config.alpha,
                                         speed_m_s=wind[0], direction_from_deg=wind[1])
        for i, value in enumerate(values):
            if value is None:
                continue
            if wind is None:
                scores[ids[i], ts] = _Score(None, None, ())
                continue
            weights = matrices[wind][i]
            expected, _ = expected_value(values, weights)
            neighbors = tuple(ids[j] for j, item in enumerate(values) if item is not None and weights[j] > 0)
            residual = value - expected if expected is not None else None
            scores[ids[i], ts] = _Score(expected, residual, neighbors)
    return scores


def _reference(station: str, ts: datetime, readings: Readings, config: DetectorConfig) -> tuple[float, float] | None:
    values = [readings[station, ts - lag * HOUR] for lag in range(1, config.recent_hours + 1)
              if (station, ts - lag * HOUR) in readings]
    scale = robust_sigma(values, min_samples=3, floor=config.scale_floor)
    return (median(values), scale) if scale is not None else None


def _smooth(station: str, ts: datetime, scores: Mapping[Key, _Score], sigma: float, hours: int) -> float | None:
    window = [scores.get((station, ts - lag * HOUR)) for lag in range(hours)]
    if any(score is None or score.residual is None or len(score.neighbors) < 2 for score in window):
        return None
    return fmean(abs(score.residual) for score in window) / sigma


def _flat(
    station: str, ts: datetime, readings: Readings, score: _Score,
    baseline: Baseline, config: DetectorConfig,
) -> bool:
    def window(node: str) -> list[float] | None:
        values = [readings.get((node, ts - lag * HOUR)) for lag in range(config.persistence_hours)]
        return values if all(value is not None for value in values) else None

    values = window(station)
    if values is None or max(values) - min(values) > config.flat_tolerance:
        return False
    zero_after_nonzero = (
        max(values) == 0 and baseline.value_median is not None
        and baseline.value_median > config.scale_floor
    )
    if not zero_after_nonzero and (baseline.value_mad is None or baseline.value_mad <= config.flat_tolerance):
        return False
    # Flatness is a separate temporal signal, supported by two observed peers.
    # A regional zero or a whole steady neighborhood cannot establish a fault.
    supporting = 0
    for neighbor in score.neighbors:
        nearby = window(neighbor)
        if nearby is None:
            continue
        if zero_after_nonzero:
            supporting += min(nearby) > config.scale_floor
            continue
        changes = sum(abs(left - right) > config.flat_tolerance for left, right in zip(nearby, nearby[1:]))
        if changes >= 2 and max(nearby) - min(nearby) >= config.z_threshold * config.scale_floor:
            supporting += 1
    return supporting >= 2


def _neighbor_evidence(
    station: str, ts: datetime, readings: Readings, stations: Mapping[str, Coordinate],
    wind: tuple[float, float], score: _Score, config: DetectorConfig,
) -> tuple[tuple[PlumeEvidence, ...], bool, bool]:
    """Return (plume matches, all observed neighbors near baseline, complete evidence)."""
    matches = []
    stable, complete = True, True
    own = _reference(station, ts, readings, config)
    if own is None:
        complete = False
    rising = own is not None and readings[station, ts] - own[0] >= config.z_threshold * own[1]
    rising = rising and score.residual is not None and score.residual > 0
    speed, direction = wind
    for neighbor in score.neighbors:
        reference = _reference(neighbor, ts, readings, config)
        if reference is None:
            complete = False
            continue
        center, scale = reference
        threshold = config.z_threshold * scale
        current_rise = readings[neighbor, ts] - center
        stable = stable and abs(current_rise) < threshold
        alignment = wind_alignment(stations[station], stations[neighbor], direction_from_deg=direction)
        if speed == 0 or alignment <= 1e-12:
            continue
        travel = haversine_km(stations[station], stations[neighbor]) / (speed * 3.6)
        lags = [lag for lag in (1, 2, 3) if abs(lag - travel) <= config.lag_tolerance_hours]
        for lag in lags:
            future = readings.get((neighbor, ts + lag * HOUR))
            if future is None:
                complete = False
                continue
            rise = future - center
            stable = stable and abs(rise) < threshold
            if rising and rise >= threshold and current_rise < threshold:
                matches.append(PlumeEvidence(neighbor, ts + lag * HOUR, lag, travel, alignment, rise, center))
    return tuple(matches), stable, complete


def classify(
    stations: Mapping[str, Coordinate], readings: Readings, weather: Weather, *,
    baseline_start: datetime, baseline_end: datetime, start: datetime, end: datetime,
    config: DetectorConfig,
) -> DetectionRun:
    """Fit an earlier baseline and classify [start, end), emitting observed rows only.

    Baseline and output windows are half-open UTC hours and must not overlap.
    Supply later readings through end + 3 hours for retrospective plume checks.
    The caller selects the presumed-healthy baseline; this function cannot prove
    its health. Missing/sparse evidence keeps VALID with low_confidence=True.
    """
    baseline_start, baseline_end, start, end = map(utc_hour, (baseline_start, baseline_end, start, end))
    if not baseline_start < baseline_end <= start < end:
        raise ValueError("Require baseline_start < baseline_end <= start < end")
    readings, weather = _inputs(stations, readings, weather)
    scores = _score_hours(stations, readings, weather, config)
    baselines = {}
    for station in sorted(stations):
        residuals = [score.residual for (node, ts), score in scores.items()
                     if node == station and baseline_start <= ts < baseline_end
                     and score.residual is not None and len(score.neighbors) >= 2]
        values = [value for (node, ts), value in readings.items()
                  if node == station and baseline_start <= ts < baseline_end]
        baselines[station] = Baseline(
            len(residuals), robust_sigma(residuals, min_samples=config.min_baseline_samples, floor=config.scale_floor),
            median(values) if values else None,
            median(abs(value - median(values)) for value in values) if values else None,
        )
    records = []
    # Include earlier detection context so an arrival at the output-window start
    # can be linked to its source. Never classify the baseline itself as context.
    context_start = max(baseline_end, start - 3 * HOUR)
    for (station, ts), score in sorted(scores.items()):
        if context_start <= ts < end:
            records.append(_classify_record(station, ts, score, baselines[station],
                                            stations, readings, weather, scores, config))
    arrivals: dict[Key, list[Key]] = {}
    for record in records:
        if record.label == "VERIFIED_PLUME_EVENT":
            for item in record.plume_evidence:
                arrivals.setdefault((item.station_id, item.ts), []).append((record.station_id, record.ts))
    output = []
    for record in records:
        if record.ts < start:
            continue
        sources = tuple(sorted(set(arrivals.get((record.station_id, record.ts), []))))
        if sources:
            record = replace(record, plume_sources=sources)
        if record.label == "SENSOR_FAULT_DRIFT" and sources:
            # A supported source explains this rise. The receiver may have no
            # further downstream observation, so do not invent plume certainty.
            record = replace(record, label="VALID", low_confidence=True, reason="arrival_of_supported_plume")
        output.append(record)
    return DetectionRun(tuple(output), baselines)


def _classify_record(
    station: str, ts: datetime, score: _Score, baseline: Baseline,
    stations: Mapping[str, Coordinate], readings: Readings, weather: Weather,
    scores: Mapping[Key, _Score], config: DetectorConfig,
) -> Classification:
    sigma = baseline.sigma
    z = abs(score.residual) / sigma if score.residual is not None and sigma is not None else None
    smoothed = _smooth(station, ts, scores, sigma, config.persistence_hours) if sigma is not None else None
    if any(value is not None and not math.isfinite(value) for value in (z, smoothed)):
        raise ValueError("Score overflow: scale_floor is too small")
    wind = weather.get(ts)

    def result(label: Label, low: bool, reason: str, evidence: tuple[PlumeEvidence, ...] = ()) -> Classification:
        return Classification(station, ts, readings[station, ts], score.expected, score.residual, z,
                              label, len(score.neighbors), wind[0] if wind else None, wind[1] if wind else None,
                              low, reason, sigma, smoothed, evidence)

    if wind is None:
        return result("VALID", True, "missing_weather")
    if len(score.neighbors) < 2:
        return result("VALID", True, "fewer_than_two_neighbors")
    if sigma is None:
        return result("VALID", True, "insufficient_baseline")
    flat = _flat(station, ts, readings, score, baseline, config)
    if flat:
        # Changing peers support a stuck-sensor hypothesis; they must not veto
        # it via the spatial anomaly/plume checks below. No future data needed.
        return result("SENSOR_FAULT_DRIFT", False, "suspected_stuck_or_zero")
    persistent = smoothed is not None and smoothed >= config.z_threshold
    if persistent:
        # Persistence requires sustained, same-sign disagreement. One resolved
        # spike or plume must not cause trailing fault labels via its mean alone.
        residuals = [scores[station, ts - lag * HOUR].residual for lag in range(config.persistence_hours)]
        persistent = all(value >= config.scale_floor for value in residuals) or all(
            value <= -config.scale_floor for value in residuals
        )
    if z < config.z_threshold and not persistent:
        return result("VALID", False, "within_threshold")
    matches, stable, complete = _neighbor_evidence(station, ts, readings, stations, wind, score, config)
    if z >= config.z_threshold and matches:
        return result("VERIFIED_PLUME_EVENT", False, "downwind_lagged_rise", matches)
    if not complete:
        return result("VALID", True, "incomplete_neighbor_evidence")
    if not stable:
        return result("VALID", True, "neighbors_also_changed")
    reason = "suspected_persistent_drift" if persistent else "suspected_isolated_anomaly"
    return result("SENSOR_FAULT_DRIFT", False, reason)
