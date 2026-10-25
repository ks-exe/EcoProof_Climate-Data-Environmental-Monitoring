"""Reproducible injection evaluation; no metrics without actual input observations."""

from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random
from typing import Any
from uuid import uuid4

import duckdb

from ecoproof.config import PROJECT_ROOT, Settings
from ecoproof.detect.classifier import DetectionRun, DetectorConfig, HOUR, Key, Readings, Weather, classify, utc_hour
from ecoproof.detect.inject import FAULT_KINDS, Injection, inject_fault, inject_plume
from ecoproof.graph.geo import Coordinate, adjacency_matrix
from ecoproof.transform.gold import read_silver_inputs
from ecoproof.transform.validation import number


class EvaluationUnavailable(ValueError):
    """The requested experiment cannot be constructed from the available observations."""


@dataclass(frozen=True)
class EvaluationConfig:
    cases_per_type: int = 3
    seed: int = 42
    fault_hours: int = 12
    spike_delta: float = 100.0
    drift_delta: float = 30.0
    degradation_factor: float = 0.7
    plume_delta: float = 100.0
    plume_decay: float = 0.5
    plume_neighbors: int = 2
    threshold: float = 150.0

    def __post_init__(self) -> None:
        for name in ("cases_per_type", "plume_neighbors"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.seed) is not int or type(self.fault_hours) is not int or self.fault_hours < 5:
            raise ValueError("seed must be an integer and fault_hours an integer >= 5")
        for name in ("spike_delta", "drift_delta", "plume_delta"):
            if number(getattr(self, name), name, 0) == 0:
                raise ValueError(f"{name} must be positive")
        number(self.degradation_factor, "degradation_factor", 0.6, 0.8)
        if not 0 < number(self.plume_decay, "plume_decay") < 1:
            raise ValueError("plume_decay must be between 0 and 1 exclusively")
        number(self.threshold, "threshold", 0, 1500)


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def metrics(tp: int, fp: int, tn: int, fn: int) -> dict[str, Any]:
    """Undefined ratios are null. With positives but no detections, F1 is zero."""
    if any(type(value) is not int or value < 0 for value in (tp, fp, tn, fn)):
        raise ValueError("Confusion counts must be nonnegative integers")
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if tp + fn else None,
            "false_positive_rate": fp / (fp + tn) if fp + tn else None}


def confusion(universe: set[Key], truth: set[Key], predicted: set[Key]) -> dict[str, Any]:
    if not truth <= universe or not predicted <= universe:
        raise ValueError("Truth and predictions must refer to scored observations")
    return metrics(len(truth & predicted), len(predicted - truth),
                   len(universe - truth - predicted), len(truth - predicted))


def score_predictions(run: DetectionRun, readings: Readings, truth: set[Key], threshold: float) -> dict[str, dict]:
    universe = {(row.station_id, row.ts) for row in run.records}
    predicted = {(row.station_id, row.ts) for row in run.records if row.label == "SENSOR_FAULT_DRIFT"}
    low = {(row.station_id, row.ts) for row in run.records if row.low_confidence}
    model = confusion(universe, truth, predicted)
    model.update({"low_confidence_count": len(low), "low_confidence_fault_count": len(low & truth),
                  "confident_fraction": (len(universe) - len(low)) / len(universe) if universe else None})
    baseline = confusion(universe, truth, {key for key in universe if readings[key] > threshold})
    return {"ecoproof": model, "threshold": baseline}


def _eligible(
    stations: Mapping[str, Coordinate], readings: Readings, weather: Weather, baselines: dict,
    start: datetime, end: datetime, detector: DetectorConfig, config: EvaluationConfig,
) -> tuple[list[Key], dict[str, int]]:
    ids = sorted(stations)
    graph = adjacency_matrix([stations[node] for node in ids], sigma_km=detector.sigma_km, tau_km=detector.tau_km)
    neighbors = {node: [ids[j] for j, weight in enumerate(graph[i]) if weight > 0] for i, node in enumerate(ids)}
    reasons = Counter()
    candidates = []
    for key in sorted(readings):
        node, ts = key
        if not start <= ts or ts + config.fault_hours * HOUR > end:
            continue
        if baselines[node].sigma is None:
            reasons['insufficient_baseline'] += 1
            continue
        times = [ts + offset * HOUR for offset in range(-detector.recent_hours, config.fault_hours + 3)]
        if any((node, hour) not in readings or hour not in weather for hour in times):
            reasons['incomplete_source_or_weather'] += 1
            continue
        nearby = sum(all((neighbor, hour) in readings for hour in times) for neighbor in neighbors[node])
        if nearby < 2:
            reasons['fewer_than_two_complete_neighbors'] += 1
            continue
        candidates.append(key)
    return candidates, dict(reasons)


def _plan(
    candidates: list[Key], stations: Mapping[str, Coordinate], readings: Readings, weather: Weather,
    detector: DetectorConfig, config: EvaluationConfig,
) -> tuple[list[Injection], dict]:
    order = list(candidates)
    random.Random(config.seed).shuffle(order)
    plans, rejections = [], {}
    for kind in (*FAULT_KINDS, 'plume'):
        selected = []
        rejected = Counter()
        for node, ts in order:
            try:
                if kind == 'plume':
                    injection = inject_plume(readings, stations, weather, station_id=node, start=ts,
                                             amplitude=config.plume_delta, decay=config.plume_decay,
                                             max_neighbors=config.plume_neighbors, tau_km=detector.tau_km,
                                             lag_tolerance_hours=detector.lag_tolerance_hours)
                else:
                    injection = inject_fault(readings, kind=kind, station_id=node, start=ts,
                                             hours=1 if kind == 'spike' else config.fault_hours,
                                             spike_delta=config.spike_delta, drift_delta=config.drift_delta,
                                             degradation_factor=config.degradation_factor)
                selected.append(injection)
            except ValueError as exc:
                rejected[str(exc)] += 1
                continue
            if len(selected) == config.cases_per_type:
                break
        if len(selected) < config.cases_per_type:
            raise EvaluationUnavailable(f"Only {len(selected)} eligible {kind} cases; requested {config.cases_per_type}. Rejections: {dict(rejected)}")
        plans.extend(selected)
        rejections[kind] = dict(rejected)
    return plans, rejections


def _fingerprint(stations: Mapping[str, Coordinate], readings: Readings, weather: Weather) -> str:
    # A reproducibility fingerprint, not a Merkle record hash. Match the project's
    # sorted, compact, UTC/four-decimal canonicalization convention.
    payload = {"stations": [[node, *(f'{value:.4f}' for value in point)] for node, point in sorted(stations.items())],
               "readings": [[node, _iso(ts), f'{value:.4f}'] for (node, ts), value in sorted(readings.items())],
               "weather": [[_iso(ts), *(f'{value:.4f}' for value in wind)] for ts, wind in sorted(weather.items())]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def evaluate_dataset(
    stations: Mapping[str, Coordinate], readings: Readings, weather: Weather, *,
    baseline_start: datetime, baseline_end: datetime, start: datetime, end: datetime,
    detector: DetectorConfig, config: EvaluationConfig, input_kind: str,
) -> dict[str, Any]:
    """Score independent intervention copies and full-window presumed-negative background.

    Cleanliness is a caller assumption, not an inferred label. Position selection
    uses availability/geometry and a seed, never classifier success or failure.
    """
    if input_kind not in ('silver_observations', 'synthetic_fixture'):
        raise ValueError("input_kind must identify Silver observations or a synthetic fixture")
    baseline_start, baseline_end, start, end = map(utc_hour, (baseline_start, baseline_end, start, end))
    if not baseline_start < baseline_end <= start < end:
        raise ValueError("Require baseline_start < baseline_end <= start < end")
    if end - start < timedelta(days=7):
        raise EvaluationUnavailable("Evaluation needs at least a seven-day output window plus earlier baseline and later context")
    # Validate inputs and evaluate the unchanged control before selecting interventions.
    arguments = dict(baseline_start=baseline_start, baseline_end=baseline_end, start=start, end=end, config=detector)
    clean = classify(stations, readings, weather, **arguments)
    coverage = []
    for node in sorted(stations):
        times = [row.ts for row in clean.records if row.station_id == node]
        coverage.append({"station_id": node, "observed_hours": len(times), "utc_dates": len({ts.date() for ts in times})})
    if sum(row['utc_dates'] >= 7 for row in coverage) < 8:
        raise EvaluationUnavailable("Evaluation needs at least 8 stations with observations on 7 UTC dates; station coverage is insufficient")
    candidates, eligibility_rejections = _eligible(stations, readings, weather, clean.baselines, start, end, detector, config)
    plans, injection_rejections = _plan(candidates, stations, readings, weather, detector, config)
    cases = []
    for index, injection in enumerate(plans):
        run = classify(stations, injection.readings, weather, **arguments)
        if run.baselines != clean.baselines:
            raise RuntimeError("Injection changed baseline calibration")
        scored = {(row.station_id, row.ts): row for row in run.records}
        affected = {(change.station_id, change.ts) for change in injection.changes}
        if not affected <= scored.keys():
            raise RuntimeError("An injected observation was not scored")
        changes = [{**asdict(change), 'ts': _iso(change.ts), 'label': scored[change.station_id, change.ts].label,
                    'low_confidence': scored[change.station_id, change.ts].low_confidence}
                   for change in injection.changes]
        case = {'case_id': f'{injection.kind}-{index + 1}', 'kind': injection.kind,
                'parameters': injection.parameters, 'interventions': changes,
                'actually_changed': sum(change.original != change.injected for change in injection.changes),
                'scored_rows': len(scored), 'methods': score_predictions(run, injection.readings, set(injection.fault_keys), config.threshold)}
        if injection.kind == 'plume':
            case['plume_control'] = {
                'affected_observations': len(affected),
                'ecoproof_faults_on_plume': sum(scored[key].label == 'SENSOR_FAULT_DRIFT' for key in affected),
                'threshold_faults_on_plume': sum(injection.readings[key] > config.threshold for key in affected),
                'source_labels': [scored[change.station_id, change.ts].label for change in injection.changes if change.role == 'plume_source'],
                'low_confidence_on_plume': sum(scored[key].low_confidence for key in affected),
            }
        cases.append(case)
    summary = {}
    for kind in (*FAULT_KINDS, 'plume'):
        group = [case for case in cases if case['kind'] == kind]
        summary[kind] = {'case_count': len(group), 'methods': {}}
        for method in ('ecoproof', 'threshold'):
            counts = [sum(case['methods'][method][name] for case in group) for name in ('tp', 'fp', 'tn', 'fn')]
            summary[kind]['methods'][method] = metrics(*counts)
        summary[kind]['low_confidence_count'] = sum(case['methods']['ecoproof']['low_confidence_count'] for case in group)
    plume_cases = [case['plume_control'] for case in cases if case['kind'] == 'plume']
    return {'schema_version': 1, 'status': 'complete', 'input_kind': input_kind, 'synthetic_interventions': True,
            'baseline_start_utc': _iso(baseline_start), 'baseline_end_exclusive_utc': _iso(baseline_end),
            'start_utc': _iso(start), 'end_exclusive_utc': _iso(end), 'detector_config': asdict(detector),
            'evaluation_config': asdict(config), 'input_fingerprint_sha256': _fingerprint(stations, readings, weather),
            'station_coverage': coverage, 'candidate_count': len(candidates),
            'eligibility_rejections': eligibility_rejections, 'injection_rejections': injection_rejections,
            'unchanged_control': score_predictions(clean, readings, set(), config.threshold), 'cases': cases, 'metrics': summary,
            'plume_negative_control_passed': all(case['ecoproof_faults_on_plume'] == 0 for case in plume_cases),
            'limitations': [
                'Faults and plume patterns are synthetic. Untouched observations are presumed healthy, not ground-truth fault-free.',
                'Metrics cover every observed output row per independent copy, including presumed-negative background; copies reuse that background.',
                'Low-confidence fault misses count as false negatives. Confidence counts are reported separately.',
                'Candidate eligibility requires baseline, weather, source history and two complete neighbors; no prediction-based selection.',
                'Positions and parameters are fixed before scoring. This run does not tune parameters or estimate real-world fault prevalence.',
                'Plume pass/fail measures false fault calls, not proof of atmospheric transport. Source labels and low-confidence counts are separate.',
                'Undefined ratios are null. Precision/recall/F1 on presumed-clean background are not independently labeled field accuracy.',
            ]}


def save_report(report: dict[str, Any], directory: Path) -> tuple[Path, Path]:
    """Publish JSON last, pointing to a completed immutable chart. Preserve prior results on a blocked attempt."""
    from ecoproof.detect.plot import render_evaluation

    directory.mkdir(parents=True, exist_ok=True)
    target = directory / 'eval.json'
    if report['status'] != 'complete' and target.exists():
        previous = json.loads(target.read_text(encoding='utf-8'))
        if previous.get('status') == 'complete':
            target = directory / 'eval.attempt.json'
    token = uuid4().hex
    chart = directory / f'eval-{token}.png'
    staged = directory / f'.eval-{token}.json'
    payload = {**report, 'generated_at_utc': _iso(datetime.now(timezone.utc)), 'chart': chart.name}
    # Serialization fails before touching a published report or chart.
    content = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)
    try:
        staged.write_text(content, encoding='utf-8')
        render_evaluation(json.loads(staged.read_text(encoding='utf-8')), chart)
        staged.replace(target)
    except Exception:
        staged.unlink(missing_ok=True)
        chart.unlink(missing_ok=True)
        raise
    return target, chart


def run_evaluation(
    settings: Settings, *, region_id: str, baseline_start: datetime, baseline_end: datetime,
    start: datetime, end: datetime, detector: DetectorConfig, config: EvaluationConfig,
    report_dir: Path = PROJECT_ROOT / 'reports',
) -> dict[str, Any]:
    """Read Silver only; publish a blocked status, never invented metrics, if data is insufficient."""
    # Reject bad arguments before classifying a failure as a data availability issue.
    bounds = tuple(map(utc_hour, (baseline_start, baseline_end, start, end)))
    if not region_id.strip() or not bounds[0] < bounds[1] <= bounds[2] < bounds[3]:
        raise ValueError("Require a region and baseline_start < baseline_end <= start < end")
    try:
        stations, readings, weather, raw_count = read_silver_inputs(settings, region_id, bounds[0], bounds[3])
        report = evaluate_dataset(stations, readings, weather, baseline_start=bounds[0], baseline_end=bounds[1],
                                  start=bounds[2], end=bounds[3], detector=detector, config=config,
                                  input_kind='silver_observations')
        report['raw_input_rows_with_context'] = raw_count
    except (EvaluationUnavailable, duckdb.Error, OSError, ValueError) as exc:
        report = {'schema_version': 1, 'status': 'blocked', 'input_kind': 'silver_observations',
                  'synthetic_interventions': True, 'reason': str(exc), 'metrics': None, 'cases': [],
                  'baseline_start_utc': _iso(bounds[0]), 'baseline_end_exclusive_utc': _iso(bounds[1]),
                  'start_utc': _iso(bounds[2]), 'end_exclusive_utc': _iso(bounds[3]),
                  'detector_config': asdict(detector), 'evaluation_config': asdict(config),
                  'plume_negative_control_passed': None}
    report['region_id'] = region_id
    path, chart = save_report(report, report_dir)
    return {'status': report['status'], 'reason': report.get('reason'), 'report': str(path), 'chart': str(chart),
            'case_count': len(report['cases']), 'plume_negative_control_passed': report['plume_negative_control_passed']}


def main() -> None:
    import argparse
    from ecoproof.config import load_settings

    parser = argparse.ArgumentParser(description='Evaluate synthetic interventions on copies of presumed-clean Silver observations.')
    parser.add_argument('--region', required=True)
    for name in ('baseline-start', 'baseline-end', 'start', 'end'):
        parser.add_argument(f'--{name}', type=datetime.fromisoformat, required=True)
    parser.add_argument('--sigma-km', type=float, required=True)
    parser.add_argument('--alpha', type=float, required=True)
    parser.add_argument('--tau-km', type=float, default=20.0)
    parser.add_argument('--z-threshold', type=float, default=2.5)
    parser.add_argument('--scale-floor', type=float, default=1.0)
    parser.add_argument('--min-baseline-samples', type=int, default=24)
    parser.add_argument('--cases-per-type', type=int, default=3)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--fault-hours', type=int, default=12)
    parser.add_argument('--threshold', type=float, default=150.0)
    parser.add_argument('--report-dir', type=Path, default=PROJECT_ROOT / 'reports')
    args = parser.parse_args()
    try:
        detector = DetectorConfig(sigma_km=args.sigma_km, alpha=args.alpha, tau_km=args.tau_km,
                                  z_threshold=args.z_threshold, scale_floor=args.scale_floor,
                                  min_baseline_samples=args.min_baseline_samples)
        config = EvaluationConfig(cases_per_type=args.cases_per_type, seed=args.seed,
                                  fault_hours=args.fault_hours, threshold=args.threshold)
        result = run_evaluation(load_settings(), region_id=args.region, baseline_start=args.baseline_start,
                                baseline_end=args.baseline_end, start=args.start, end=args.end,
                                detector=detector, config=config, report_dir=args.report_dir)
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from None
    print(json.dumps(result, indent=2))
    if result['status'] != 'complete' or result['plume_negative_control_passed'] is False:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
