"""Computed metric and experiment checks; synthetic metrics never enter project reports."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import pytest

from ecoproof.config import Settings
from ecoproof.detect.classifier import Classification, DetectionRun, DetectorConfig
from ecoproof.detect.evaluate import (
    EvaluationConfig, EvaluationUnavailable, confusion, evaluate_dataset, main, metrics, run_evaluation, save_report, score_predictions,
)


START = datetime(2026, 10, 1, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)
DETECTOR = DetectorConfig(sigma_km=10, alpha=.5)
CONFIG = EvaluationConfig(cases_per_type=1, seed=42)


def inputs() -> tuple[dict, dict, dict]:
    stations = {str(node): (0.0, node * .015) for node in range(8)}
    readings = {(node, START + hour * HOUR): 20.0 + (hour % 5) * .2 for node in stations for hour in range(195)}
    weather = {START + hour * HOUR: (2.0, 270.0) for hour in range(195)}
    return stations, readings, weather


def evaluate(stations: dict, readings: dict, weather: dict, **kwargs) -> dict:
    return evaluate_dataset(stations, readings, weather, baseline_start=START, baseline_end=START + 24 * HOUR,
                            start=START + 24 * HOUR, end=START + 192 * HOUR, detector=DETECTOR,
                            config=kwargs.get('config', CONFIG), input_kind='synthetic_fixture')


@pytest.fixture(scope='module')
def experiment() -> dict:
    return evaluate(*inputs())


def test_known_confusion_counts_and_undefined_ratios() -> None:
    result = metrics(3, 1, 4, 2)
    assert result['precision'] == .75
    assert result['recall'] == .6
    assert result['f1'] == pytest.approx(2 / 3)
    assert result['false_positive_rate'] == .2
    assert metrics(0, 0, 4, 2)['precision'] is None
    assert metrics(0, 0, 4, 2)['recall'] == 0
    assert metrics(0, 0, 4, 2)['f1'] == 0
    assert metrics(0, 0, 4, 0)['f1'] is None
    assert metrics(0, 0, 0, 0)['false_positive_rate'] is None
    universe = {('a', START), ('b', START), ('c', START)}
    assert confusion(universe, {('a', START)}, {('a', START), ('b', START)}) == metrics(1, 1, 1, 0)
    with pytest.raises(ValueError):
        confusion(universe, {('missing', START)}, set())


def test_low_confidence_positive_counts_as_miss_and_threshold_is_strict() -> None:
    readings = {('a', START): 150.0, ('b', START): 151.0, ('c', START): 0.0}
    records = tuple(Classification(node, ts, value, None, None, None, 'VALID', 1, 2.0, 270.0,
                                   node == 'b', 'test', None, None) for (node, ts), value in readings.items())
    results = score_predictions(DetectionRun(records, {}), readings, {('b', START)}, 150)
    assert results['ecoproof']['fn'] == 1 and results['ecoproof']['low_confidence_fault_count'] == 1
    assert results['ecoproof']['recall'] == results['ecoproof']['f1'] == 0
    assert results['threshold'] == metrics(1, 0, 2, 0)


def test_each_fault_and_plume_are_evaluated_without_hiding_misses(experiment: dict) -> None:
    assert experiment['status'] == 'complete' and experiment['input_kind'] == 'synthetic_fixture'
    assert len(experiment['cases']) == 6
    for case in experiment['cases']:
        for result in case['methods'].values():
            assert result['tp'] + result['fp'] + result['tn'] + result['fn'] == 1344
        positives = 0 if case['kind'] == 'plume' else len(case['interventions'])
        for result in case['methods'].values():
            assert result['tp'] + result['fn'] == positives
        assert case['methods']['ecoproof']['low_confidence_fault_count'] <= case['methods']['ecoproof']['fn']
        # All injected values stay below 150, so this naive baseline misses every fault.
        assert case['methods']['threshold']['tp'] == 0
        assert case['methods']['threshold']['fn'] == positives
        assert all(item['ts'] >= '2026-10-02T00:00:00Z' for item in case['interventions'])
    assert experiment['plume_negative_control_passed']
    plume = next(case for case in experiment['cases'] if case['kind'] == 'plume')
    assert plume['plume_control']['ecoproof_faults_on_plume'] == 0
    assert plume['plume_control']['source_labels'] == ['VERIFIED_PLUME_EVENT']
    assert experiment['metrics']['plume']['methods']['ecoproof']['f1'] is None


def test_reproducible_seed_input_order_and_no_mutation(experiment: dict) -> None:
    stations, readings, weather = inputs()
    before = readings.copy()
    result = evaluate(dict(reversed(list(stations.items()))), dict(reversed(list(readings.items()))), weather)
    assert result == experiment
    assert readings == before
    alternate = evaluate(stations, readings, weather, config=replace(CONFIG, seed=7))
    assert alternate['input_fingerprint_sha256'] == experiment['input_fingerprint_sha256']
    assert [case['parameters'] for case in alternate['cases']] != [case['parameters'] for case in experiment['cases']]


def test_default_three_cases_preserve_full_denominators() -> None:
    report = evaluate(*inputs(), config=EvaluationConfig())
    assert len(report['cases']) == 18
    for kind, group in report['metrics'].items():
        result = group['methods']['threshold']
        assert group['case_count'] == 3
        assert sum(result[name] for name in ('tp', 'fp', 'tn', 'fn')) == 3 * 1344
        assert result['fn'] == (0 if kind == 'plume' else 3 if kind == 'spike' else 36)


def test_inadequate_region_and_impossible_controls_do_not_make_metrics() -> None:
    stations, readings, weather = inputs()
    stations.pop('7')
    readings = {key: value for key, value in readings.items() if key[0] in stations}
    with pytest.raises(EvaluationUnavailable, match='at least 8'):
        evaluate(stations, readings, weather)
    stations, readings, weather = inputs()
    weather = {ts: (0, 0) for ts in weather}
    with pytest.raises(EvaluationUnavailable, match='eligible plume'):
        evaluate(stations, readings, weather)


def test_failed_plume_control_is_saved_as_failure_without_reselecting(experiment: dict, monkeypatch, capsys) -> None:
    from ecoproof.detect import evaluate as module
    actual = module.classify
    calls = []
    def faulty_classifier(*args, **kwargs):
        calls.append(1)
        run = actual(*args, **kwargs)
        return replace(run, records=tuple(replace(row, label='SENSOR_FAULT_DRIFT')
                                           if row.label == 'VERIFIED_PLUME_EVENT' else row for row in run.records))
    monkeypatch.setattr(module, 'classify', faulty_classifier)
    report = evaluate(*inputs())
    assert report['status'] == 'complete' and report['plume_negative_control_passed'] is False
    assert len(calls) == 7  # unchanged control + six independent cases; no outcome-based retry
    assert [case['parameters'] for case in report['cases']] == [case['parameters'] for case in experiment['cases']]
    monkeypatch.setattr(module, 'run_evaluation', lambda *args, **kwargs: {
        'status': report['status'], 'plume_negative_control_passed': report['plume_negative_control_passed']})
    monkeypatch.setattr(sys, 'argv', ['eval', '--region', 'test', '--baseline-start', '2026-10-01T00:00:00Z',
                                    '--baseline-end', '2026-10-02T00:00:00Z', '--start', '2026-10-02T00:00:00Z',
                                    '--end', '2026-10-09T00:00:00Z', '--sigma-km', '10', '--alpha', '.5'])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert json.loads(capsys.readouterr().out)['plume_negative_control_passed'] is False


def test_saved_chart_and_json_are_from_computed_report(experiment: dict, tmp_path: Path) -> None:
    path, chart = save_report(experiment, tmp_path)
    saved = json.loads(path.read_text())
    assert saved['metrics'] == experiment['metrics']
    assert saved['chart'] == chart.name
    assert chart.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    assert saved['input_kind'] == 'synthetic_fixture'


def test_blocked_attempt_preserves_successful_report(experiment: dict, tmp_path: Path) -> None:
    successful, _ = save_report(experiment, tmp_path)
    before = successful.read_bytes()
    blocked, _ = save_report({'status': 'blocked', 'reason': 'No air readings', 'metrics': None, 'cases': []}, tmp_path)
    assert blocked.name == 'eval.attempt.json'
    assert successful.read_bytes() == before
    assert json.loads(blocked.read_text())['metrics'] is None


def test_chart_failure_preserves_existing_report_and_cleans_staging(experiment: dict, tmp_path: Path, monkeypatch) -> None:
    from ecoproof.detect import plot
    path, _ = save_report(experiment, tmp_path)
    before = {file: file.read_bytes() for file in tmp_path.iterdir()}
    def fail(*args):
        raise OSError('test chart failure')
    monkeypatch.setattr(plot, 'render_evaluation', fail)
    with pytest.raises(OSError, match='test chart failure'):
        save_report(experiment, tmp_path)
    assert {file: file.read_bytes() for file in tmp_path.iterdir()} == before
    assert path.read_bytes() == before[path]


def test_missing_real_data_produces_blocked_status_no_fake_metrics(tmp_path: Path) -> None:
    result = run_evaluation(Settings(tmp_path / 'missing-data'), region_id='test', baseline_start=START,
                            baseline_end=START + 24 * HOUR, start=START + 24 * HOUR, end=START + 192 * HOUR,
                            detector=DETECTOR, config=CONFIG, report_dir=tmp_path / 'reports')
    assert result['status'] == 'blocked'
    saved = json.loads(Path(result['report']).read_text())
    assert saved['metrics'] is None and saved['cases'] == []
    assert saved['plume_negative_control_passed'] is None
    assert Path(result['chart']).is_file()


def test_cli_returns_failure_when_observations_missing(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv('ECOPROOF_DATA_DIR', str(tmp_path / 'missing'))
    monkeypatch.setattr(sys, 'argv', ['eval', '--region', 'test', '--baseline-start', '2026-10-01T00:00:00Z',
                                    '--baseline-end', '2026-10-02T00:00:00Z', '--start', '2026-10-02T00:00:00Z',
                                    '--end', '2026-10-09T00:00:00Z', '--sigma-km', '10', '--alpha', '.5',
                                    '--report-dir', str(tmp_path / 'reports')])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert json.loads(capsys.readouterr().out)['status'] == 'blocked'
