"""Intervention truth, bounds, geometry, and immutability checks on synthetic input."""

from datetime import datetime, timedelta, timezone

import pytest

from ecoproof.detect.inject import inject_fault, inject_plume


START = datetime(2026, 10, 2, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)


def readings() -> dict:
    return {(node, START + index * HOUR): float(20 + index) for node in ('a', 'b', 'c') for index in range(-1, 15)}


@pytest.mark.parametrize('kind,expected', [('stuck', [19, 19, 19]), ('zero', [0, 0, 0]),
                                         ('spike', [120, 121, 122]), ('drift', [30, 41, 52]),
                                         ('degradation', [14, 14.7, 15.4])])
def test_fault_transformations_truth_and_copy(kind: str, expected: list) -> None:
    original = readings()
    before = original.copy()
    result = inject_fault(original, kind=kind, station_id='a', start=START, hours=3)
    assert [result.readings['a', START + index * HOUR] for index in range(3)] == pytest.approx(expected)
    assert result.fault_keys == frozenset(('a', START + index * HOUR) for index in range(3))
    assert len(result.changes) == 3
    assert result.readings is not original and original == before
    assert all(result.readings[key] == value for key, value in original.items() if key not in result.fault_keys)


def test_stuck_truth_includes_coincident_unchanged_sample() -> None:
    original = readings()
    original['a', START] = 19
    result = inject_fault(original, kind='stuck', station_id='a', start=START, hours=3)
    assert result.changes[0].original == result.changes[0].injected
    assert ('a', START) in result.fault_keys


@pytest.mark.parametrize('problem', ['gap', 'previous_gap', 'no_effect', 'overflow', 'bad_hours', 'naive'])
def test_unconstructable_injection_fails_without_mutation(problem: str) -> None:
    original = readings()
    args = dict(kind='stuck', station_id='a', start=START, hours=3)
    if problem == 'gap':
        del original['a', START + HOUR]
    elif problem == 'previous_gap':
        del original['a', START - HOUR]
    elif problem == 'no_effect':
        original = {key: 20.0 for key in original}
    elif problem == 'overflow':
        original['a', START] = 1490
        args['kind'] = 'spike'
    elif problem == 'bad_hours':
        args['hours'] = 0
    else:
        args['start'] = START.replace(tzinfo=None)
    before = original.copy()
    with pytest.raises(ValueError):
        inject_fault(original, **args)
    assert original == before


def test_plume_modifies_only_source_and_observed_downwind_arrival() -> None:
    original = readings()
    stations = {'a': (0, 0), 'b': (0, .1), 'c': (0, -.1)}
    result = inject_plume(original, stations, {START: (2, 270)}, station_id='a', start=START)
    assert not result.fault_keys
    assert result.readings['a', START] == 120
    # 11.12 km / 7.2 km/h -> nearest discrete lag is 2 hours.
    assert result.readings['b', START + 2 * HOUR] == 72
    assert [(item.station_id, item.role) for item in result.changes] == [('a', 'plume_source'), ('b', 'plume_arrival')]
    assert result.parameters['recipients'][0]['lag_hours'] == 2
    assert original == readings()


@pytest.mark.parametrize('wind', [(0, 270), (.01, 270), (2, 0)])
def test_plume_requires_viable_transport(wind: tuple) -> None:
    with pytest.raises(ValueError):
        inject_plume(readings(), {'a': (0, 0), 'b': (0, .1)}, {START: wind}, station_id='a', start=START)


def test_missing_plume_recipient_is_not_created() -> None:
    original = readings()
    del original['b', START + 2 * HOUR]
    with pytest.raises(ValueError, match='No observed downwind'):
        inject_plume(original, {'a': (0, 0), 'b': (0, .1)}, {START: (2, 270)}, station_id='a', start=START)
