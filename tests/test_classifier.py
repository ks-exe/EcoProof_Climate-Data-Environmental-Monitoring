"""Synthetic classifier acceptance cases; these are not measured detection metrics."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import math

import pytest

from ecoproof.detect.classifier import DetectorConfig, classify, expected_value, robust_sigma
from ecoproof.graph.geo import wind_alignment


ORIGIN = datetime(2026, 10, 1, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)
STATIONS = {"a": (0.0, 0.0), "b": (0.0, 0.1), "c": (0.0, -0.1)}
CONFIG = DetectorConfig(sigma_km=10.0, alpha=0.5)


def fixtures(hours: int = 40) -> tuple[dict, dict]:
    readings = {(station, ORIGIN + hour * HOUR): 20.0 for station in STATIONS for hour in range(hours)}
    weather = {ORIGIN + hour * HOUR: (2.0, 270.0) for hour in range(hours)}
    return readings, weather


def run(readings: dict, weather: dict, *, stations: dict = STATIONS,
        config: DetectorConfig = CONFIG, start: int = 24, end: int = 37):
    return classify(stations, readings, weather, baseline_start=ORIGIN,
                    baseline_end=ORIGIN + 24 * HOUR, start=ORIGIN + start * HOUR,
                    end=ORIGIN + end * HOUR, config=config)


def at(result, hour: int = 24, station: str = "a"):
    return next(row for row in result.records if row.station_id == station and row.ts == ORIGIN + hour * HOUR)


def test_expected_value_excludes_missing_and_self_but_keeps_zero() -> None:
    assert expected_value([10.0, None, 0.0, 1000.0], [1.0, 9.0, 3.0, 0.0]) == (2.5, 2)
    assert expected_value([None, 10.0], [1.0, 0.0]) == (None, 0)
    assert expected_value([10.0, 20.0], [1e308, 1e308]) == (15.0, 2)


@pytest.mark.parametrize("values,weights", [([1.0], []), ([1.0], [-1.0]), ([float('nan')], [1.0]),
                                           ([1501.0], [1.0]), ([True], [1.0]), ([1.0], [float('inf')])])
def test_invalid_weighted_mean_inputs_raise(values, weights) -> None:
    with pytest.raises(ValueError):
        expected_value(values, weights)


def test_robust_scale_known_mad_outlier_and_zero_variance() -> None:
    assert robust_sigma([-2, -1, 0, 1, 2], min_samples=5, floor=0.1) == pytest.approx(1.4826)
    assert robust_sigma([-2, -1, -1, 0, 0, 1, 1, 2, 1000], min_samples=5, floor=0.1) == pytest.approx(1.4826)
    assert robust_sigma([0.0] * 24) == 1.0
    assert robust_sigma([1.0, 2.0]) is None


@pytest.mark.parametrize("bad", [float('nan'), float('inf'), None, True])
def test_invalid_residuals_are_not_ignored(bad) -> None:
    with pytest.raises(ValueError):
        robust_sigma([bad])


def test_isolated_spike_is_suspected_fault_with_unbiased_expected_value() -> None:
    readings, weather = fixtures()
    readings['a', ORIGIN + 24 * HOUR] = 60.0
    row = at(run(readings, weather))
    assert row.expected == pytest.approx(20.0)
    assert row.residual == pytest.approx(40.0)
    assert row.z == pytest.approx(40.0)
    assert row.neighbor_count == 2
    assert row.label == 'SENSOR_FAULT_DRIFT'
    assert row.reason == 'suspected_isolated_anomaly'
    assert not row.low_confidence


@pytest.mark.parametrize("delta,expected", [(2.49, 'VALID'), (2.5, 'SENSOR_FAULT_DRIFT'), (-2.5, 'SENSOR_FAULT_DRIFT')])
def test_threshold_boundary_and_both_residual_signs(delta: float, expected: str) -> None:
    readings, weather = fixtures()
    readings['a', ORIGIN + 24 * HOUR] += delta
    assert at(run(readings, weather)).label == expected


def test_baseline_uses_only_selected_earlier_residuals() -> None:
    readings, weather = fixtures()
    clean = run(readings, weather)
    for hour in range(24, 40):
        readings['a', ORIGIN + hour * HOUR] = 500.0
    altered = run(readings, weather)
    assert altered.baselines == clean.baselines
    assert altered.baselines['a'].sample_count == 24
    assert altered.baselines['a'].sigma == 1.0


def test_healthy_baseline_mad_is_fitted_from_weighted_residuals() -> None:
    readings, weather = fixtures()
    for hour in range(24):
        readings['a', ORIGIN + hour * HOUR] += [-1.0, 0.0, 1.0][hour % 3]
    assert run(readings, weather).baselines['a'].sigma == pytest.approx(1.4826)


@pytest.mark.parametrize("missing", [1, 2])
def test_too_few_current_neighbors_never_claims_fault(missing: int) -> None:
    readings, weather = fixtures()
    readings['a', ORIGIN + 24 * HOUR] = 500.0
    for station in ('b', 'c')[:missing]:
        del readings[station, ORIGIN + 24 * HOUR]
    row = at(run(readings, weather))
    assert row.label == 'VALID' and row.low_confidence
    assert row.reason == 'fewer_than_two_neighbors'
    assert row.neighbor_count == 2 - missing
    assert row.expected == (20.0 if missing == 1 else None)


def test_missing_weather_is_not_calm_or_validated() -> None:
    readings, weather = fixtures()
    del weather[ORIGIN + 24 * HOUR]
    row = at(run(readings, weather))
    assert row.label == 'VALID' and row.low_confidence
    assert row.reason == 'missing_weather'
    assert row.expected is row.z is row.wind_speed is None


def test_sparse_baseline_returns_unknown_scale_not_a_fault() -> None:
    readings, weather = fixtures()
    del weather[ORIGIN]
    readings['a', ORIGIN + 24 * HOUR] = 500.0
    result = run(readings, weather)
    row = at(result)
    assert result.baselines['a'].sample_count == 23
    assert row.label == 'VALID' and row.low_confidence
    assert row.z is None and row.reason == 'insufficient_baseline'


def test_lagged_downwind_plume_has_evidence_and_no_trailing_source_faults() -> None:
    readings, weather = fixtures()
    readings['a', ORIGIN + 24 * HOUR] = 60.0
    readings['b', ORIGIN + 25 * HOUR] = 35.0
    result = run(readings, weather)
    row = at(result)
    assert row.label == 'VERIFIED_PLUME_EVENT' and not row.low_confidence
    evidence = row.plume_evidence[0]
    assert evidence.station_id == 'b' and evidence.lag_hours == 1
    assert evidence.travel_hours == pytest.approx(11.11950802335 / 7.2)
    assert evidence.rise == 15.0 and evidence.reference == 20.0
    assert evidence.alignment == pytest.approx(1.0)
    assert not any(item.label == 'SENSOR_FAULT_DRIFT' for item in result.records)
    # Repeat with a dense graph: downstream stations also have >= 2 neighbors.
    dense = {'a': (0.0, 0.0), 'b': (0.0, 0.05), 'c': (0.0, -0.05)}
    dense_result = run(readings, weather, stations=dense)
    assert at(dense_result).label == 'VERIFIED_PLUME_EVENT'
    assert all(item.neighbor_count == 2 for item in dense_result.records)
    assert not any(item.label == 'SENSOR_FAULT_DRIFT' for item in dense_result.records)
    arrival = at(dense_result, hour=25, station='b')
    assert arrival.low_confidence and arrival.reason == 'arrival_of_supported_plume'
    assert arrival.plume_sources == (('a', ORIGIN + 24 * HOUR),)
    sliced = run(readings, weather, stations=dense, start=25)
    assert at(sliced, hour=25, station='b') == arrival


@pytest.mark.parametrize("speed,neighbor,lag", [(0.0, 'b', 1), (2.0, 'c', 1), (10.0, 'b', 3), (0.1, 'b', 1)])
def test_rise_requires_noncalm_downwind_and_consistent_travel_time(speed: float, neighbor: str, lag: int) -> None:
    readings, weather = fixtures()
    weather[ORIGIN + 24 * HOUR] = (speed, 270.0)
    readings['a', ORIGIN + 24 * HOUR] = 60.0
    readings[neighbor, ORIGIN + (24 + lag) * HOUR] = 35.0
    assert at(run(readings, weather)).label == 'SENSOR_FAULT_DRIFT'


def test_negative_anomaly_is_not_a_pollution_plume() -> None:
    readings, weather = fixtures()
    readings['a', ORIGIN + 24 * HOUR] = 0.0
    readings['b', ORIGIN + 25 * HOUR] = 35.0
    row = at(run(readings, weather))
    assert row.label == 'VALID' and row.low_confidence
    assert row.reason == 'neighbors_also_changed'


def test_incomplete_future_or_recent_evidence_does_not_claim_isolation() -> None:
    readings, weather = fixtures(25)
    readings['a', ORIGIN + 24 * HOUR] = 60.0
    row = at(run(readings, weather, end=25))
    assert row.label == 'VALID' and row.low_confidence
    assert row.reason == 'incomplete_neighbor_evidence'

    readings, weather = fixtures()
    readings['a', ORIGIN + 31 * HOUR] = 60.0
    for hour in range(25, 31):
        del readings['b', ORIGIN + hour * HOUR]
    row = at(run(readings, weather), hour=31)
    assert row.label == 'VALID' and row.low_confidence


def test_regional_rise_and_neighbor_disagreement_do_not_cascade_faults() -> None:
    readings, weather = fixtures()
    for station in STATIONS:
        readings[station, ORIGIN + 24 * HOUR] = 60.0
    assert at(run(readings, weather)).label == 'VALID'
    readings['a', ORIGIN + 24 * HOUR] = 20.0
    row = at(run(readings, weather))
    assert row.label == 'VALID' and row.low_confidence


def test_sustained_drift_can_trigger_when_current_z_falls_below_threshold() -> None:
    readings, weather = fixtures()
    for hour, delta in zip(range(24, 29), [3.0, 3.0, 3.0, 3.0, 2.0]):
        readings['a', ORIGIN + hour * HOUR] += delta
    row = at(run(readings, weather), hour=28)
    assert row.z == pytest.approx(2.0)
    assert row.smoothed_z == pytest.approx(2.8)
    assert row.label == 'SENSOR_FAULT_DRIFT'
    assert row.reason == 'suspected_persistent_drift'


def test_persistence_requires_consecutive_hours_and_not_one_resolved_spike() -> None:
    readings, weather = fixtures()
    readings['a', ORIGIN + 24 * HOUR] = 100.0
    assert at(run(readings, weather), hour=25).label == 'VALID'
    del readings['a', ORIGIN + 26 * HOUR]
    row = at(run(readings, weather), hour=28)
    assert row.smoothed_z is None and row.label == 'VALID'


def test_zero_run_is_suspected_fault() -> None:
    readings, weather = fixtures()
    for hour in range(24, 30):
        readings['a', ORIGIN + hour * HOUR] = 0.0
    row = at(run(readings, weather), hour=28)
    assert row.label == 'SENSOR_FAULT_DRIFT'
    assert row.reason == 'suspected_stuck_or_zero'


def test_flatline_against_varying_neighbors_and_previously_varying_sensor() -> None:
    readings, weather = fixtures()
    for (station, ts) in readings:
        hour = int((ts - ORIGIN) / HOUR)
        readings[station, ts] = 20.0 + (1.5 if hour % 2 else -1.5)
    for hour in range(24, 30):
        readings['a', ORIGIN + hour * HOUR] = 20.0
    row = at(run(readings, weather), hour=28)
    assert row.z < 2.5
    assert row.label == 'SENSOR_FAULT_DRIFT' and row.reason == 'suspected_stuck_or_zero'


@pytest.mark.parametrize("stuck_value", [0.0, 20.0])
def test_supported_flatline_is_detected_during_changing_pollution_without_future_data(stuck_value: float) -> None:
    readings, weather = fixtures(29)
    for station, ts in readings:
        hour = int((ts - ORIGIN) / HOUR)
        readings[station, ts] = 20.0 + (hour % 3 - 1)
    for hour in range(24, 29):
        readings['a', ORIGIN + hour * HOUR] = stuck_value
        for neighbor in ('b', 'c'):
            readings[neighbor, ORIGIN + hour * HOUR] = 20.0 + 10 * (hour - 23)
    result = run(readings, weather, end=29)
    row = at(result, hour=28)
    assert row.label == 'SENSOR_FAULT_DRIFT'
    assert row.reason == 'suspected_stuck_or_zero' and not row.low_confidence
    # Fewer than five repeated hours cannot use the flatline reason.
    assert all(at(result, hour=hour).reason != 'suspected_stuck_or_zero' for hour in range(24, 28))


def test_regional_zero_after_positive_baseline_is_not_an_individual_flatline_fault() -> None:
    readings, weather = fixtures()
    for station in STATIONS:
        for hour in range(24, 30):
            readings[station, ORIGIN + hour * HOUR] = 0.0
    result = run(readings, weather)
    assert all(at(result, hour=28, station=node).label == 'VALID' for node in STATIONS)


@pytest.mark.parametrize("missing", ["source", "peer"])
def test_flatline_requires_consecutive_source_and_two_complete_peer_windows(missing: str) -> None:
    readings, weather = fixtures()
    for station, ts in readings:
        readings[station, ts] += 1.5 if int((ts - ORIGIN) / HOUR) % 2 else -1.5
    for hour in range(24, 30):
        readings['a', ORIGIN + hour * HOUR] = 20.0
    node = 'a' if missing == 'source' else 'c'
    del readings[node, ORIGIN + 26 * HOUR]
    row = at(run(readings, weather), hour=28)
    assert row.label == 'VALID' and row.reason != 'suspected_stuck_or_zero'


def test_single_changing_peer_does_not_establish_a_stuck_sensor() -> None:
    readings, weather = fixtures()
    for hour in range(24):
        readings['a', ORIGIN + hour * HOUR] += 1.5 if hour % 2 else -1.5
    for hour in range(24, 30):
        readings['b', ORIGIN + hour * HOUR] += 1.5 if hour % 2 else -1.5
    row = at(run(readings, weather), hour=28)
    assert row.label == 'VALID' and row.reason != 'suspected_stuck_or_zero'


@pytest.mark.parametrize("value", [0.0, 20.0])
def test_entire_neighborhood_steady_is_not_a_stuck_sensor(value: float) -> None:
    readings, weather = fixtures()
    readings = {key: value for key in readings}
    assert at(run(readings, weather), hour=28).label == 'VALID'


def test_seven_synthetic_days_eight_stations_deterministic_and_no_input_mutation() -> None:
    stations = {str(i): (0.0, i * 0.005) for i in range(8)}
    readings = {(station, ORIGIN + hour * HOUR): 20 + 2 * math.sin(hour)
                for station in stations for hour in range(24 + 168 + 3)}
    weather = {ORIGIN + hour * HOUR: (2.0, 270.0) for hour in range(24 + 168 + 3)}
    before = readings.copy()
    result = run(readings, weather, stations=stations, end=24 + 168)
    assert len(result.records) == 8 * 168
    assert all(row.label == 'VALID' and not row.low_confidence for row in result.records)
    reversed_inputs = run(dict(reversed(list(readings.items()))), weather,
                          stations=dict(reversed(list(stations.items()))), end=24 + 168)
    assert reversed_inputs == result
    assert readings == before


def test_timezone_normalization_and_no_rows_invented_for_missing_target() -> None:
    readings, weather = fixtures()
    del readings['a', ORIGIN + 24 * HOUR]
    offset = timezone(timedelta(hours=5))
    readings = {(station, ts.astimezone(offset)): value for (station, ts), value in readings.items()}
    result = run(readings, weather)
    assert not any(row.station_id == 'a' and row.ts == ORIGIN + 24 * HOUR for row in result.records)
    assert all(row.ts.tzinfo == timezone.utc for row in result.records)


@pytest.mark.parametrize("field,value", [('scale_floor', 0.0), ('scale_floor', float('nan')),
                                        ('z_threshold', -1.0), ('min_baseline_samples', 2),
                                        ('persistence_hours', True), ('alpha', -1.0), ('sigma_km', 0.0)])
def test_invalid_config_rejected(field: str, value) -> None:
    with pytest.raises(ValueError):
        replace(CONFIG, **{field: value})


def test_overlap_naive_timestamps_unknown_station_and_bad_values_rejected() -> None:
    readings, weather = fixtures()
    with pytest.raises(ValueError, match='baseline_start'):
        run(readings, weather, start=23)
    for key, value in [(('a', ORIGIN.replace(tzinfo=None)), 20.0),
                       (('a', ORIGIN + timedelta(minutes=30)), 20.0),
                       (('unknown', ORIGIN), 20.0), (('a', ORIGIN), float('nan'))]:
        altered = {**readings, key: value}
        with pytest.raises(ValueError):
            run(altered, weather)
    with pytest.raises(ValueError):
        run(readings, {**weather, ORIGIN: (float('nan'), 270.0)})


def test_public_alignment_for_plume_direction_and_coincidence() -> None:
    assert wind_alignment((0, 0), (0, .1), direction_from_deg=270) == pytest.approx(1)
    assert wind_alignment((0, 0), (0, .1), direction_from_deg=90) == pytest.approx(-1)
    assert wind_alignment((0, 0), (0, 0), direction_from_deg=90) == 0
