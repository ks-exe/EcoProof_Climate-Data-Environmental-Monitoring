"""Transport ambiguity under a falling background; synthetic evidence tests."""

from datetime import datetime, timedelta, timezone

import pytest

from ecoproof.detect.classifier import DetectorConfig, classify


ORIGIN = datetime(2026, 10, 1, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)
STATIONS = {'a': (0.0, 0.0), 'b': (0.0, 0.05), 'c': (0.0, -0.05)}
CONFIG = DetectorConfig(sigma_km=10, alpha=0.5)


def falling_background() -> tuple[dict, dict]:
    readings = {(node, ORIGIN + hour * HOUR): 20.0 for node in STATIONS for hour in range(40)}
    weather = {ORIGIN + hour * HOUR: (2.0, 270.0) for hour in range(40)}
    for hour, value in zip(range(24, 30), [80., 75., 70., 50., 35., 30.]):
        readings['b', ORIGIN + hour * HOUR] = value
    readings['a', ORIGIN + 30 * HOUR] = 120.0
    readings['c', ORIGIN + 30 * HOUR] = 30.0
    readings['b', ORIGIN + 30 * HOUR] = 25.0
    readings['b', ORIGIN + 31 * HOUR] = 70.0
    return readings, weather


def run(readings: dict, weather: dict, *, start: int = 24) -> dict:
    result = classify(STATIONS, readings, weather, baseline_start=ORIGIN,
                      baseline_end=ORIGIN + 24 * HOUR, start=ORIGIN + start * HOUR,
                      end=ORIGIN + 37 * HOUR, config=CONFIG)
    return {(row.station_id, int((row.ts - ORIGIN) / HOUR)): row for row in result.records}


def test_falling_reference_makes_lagged_arrival_uncertain_not_an_isolated_fault() -> None:
    readings, weather = falling_background()
    before = dict(readings)
    result = run(readings, weather)
    source, arrival = result['a', 30], result['b', 31]
    assert source.label == 'VALID' and source.low_confidence
    assert source.reason == 'neighbors_also_changed' and not source.plume_evidence
    assert arrival.z >= CONFIG.z_threshold and arrival.residual > 0
    assert arrival.label == 'VALID' and arrival.low_confidence
    assert arrival.reason == 'possible_upwind_transport'
    assert arrival.plume_sources == (('a', ORIGIN + 30 * HOUR),)
    assert not arrival.plume_evidence  # Ambiguity is not confirmed transport.
    assert readings == before


def test_arrival_uses_source_time_wind_and_preserves_output_slice_context() -> None:
    readings, weather = falling_background()
    weather[ORIGIN + 31 * HOUR] = (2.0, 90.0)
    full = run(readings, weather)['b', 31]
    assert full.reason == 'possible_upwind_transport'
    assert run(readings, weather, start=31)['b', 31] == full


@pytest.mark.parametrize('wind', [(0.0, 270.0), (2.0, 90.0), (0.1, 270.0)])
def test_calm_upwind_or_impossible_travel_does_not_suppress_fault(wind: tuple) -> None:
    readings, weather = falling_background()
    weather[ORIGIN + 30 * HOUR] = wind
    arrival = run(readings, weather)['b', 31]
    assert arrival.label == 'SENSOR_FAULT_DRIFT' and not arrival.plume_sources


def test_suspected_fault_source_cannot_clear_another_fault() -> None:
    readings, weather = falling_background()
    readings['c', ORIGIN + 30 * HOUR] = 20.0
    result = run(readings, weather)
    assert result['a', 30].label == 'SENSOR_FAULT_DRIFT'
    assert result['b', 31].label == 'SENSOR_FAULT_DRIFT'
    assert not result['b', 31].plume_sources


def test_no_source_anomaly_leaves_receiver_fault() -> None:
    readings, weather = falling_background()
    readings['a', ORIGIN + 30 * HOUR] = 21.0
    arrival = run(readings, weather)['b', 31]
    assert arrival.label == 'SENSOR_FAULT_DRIFT' and not arrival.plume_sources


def test_missing_source_time_receiver_reading_does_not_invent_a_step() -> None:
    readings, weather = falling_background()
    del readings['b', ORIGIN + 30 * HOUR]
    arrival = run(readings, weather)['b', 31]
    assert arrival.label == 'SENSOR_FAULT_DRIFT' and not arrival.plume_sources


def test_positive_residual_without_a_positive_step_does_not_clear_fault() -> None:
    readings, weather = falling_background()
    readings['b', ORIGIN + 29 * HOUR] = 0.0
    readings['b', ORIGIN + 30 * HOUR] = 110.0
    readings['b', ORIGIN + 31 * HOUR] = 100.0
    arrival = run(readings, weather)['b', 31]
    assert arrival.residual > 0
    assert arrival.reason == 'suspected_isolated_anomaly'
    assert arrival.label == 'SENSOR_FAULT_DRIFT' and not arrival.plume_sources


def test_negative_receiver_anomaly_is_not_explained_by_upwind_pollution() -> None:
    readings, weather = falling_background()
    readings['b', ORIGIN + 31 * HOUR] = 0.0
    arrival = run(readings, weather)['b', 31]
    assert arrival.residual < 0
    assert arrival.label == 'SENSOR_FAULT_DRIFT' and not arrival.plume_sources
