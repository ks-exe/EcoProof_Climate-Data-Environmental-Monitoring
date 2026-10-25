"""Run the frozen paired experiment documented in docs/PLUME_REVIEW.md."""

import argparse
from dataclasses import asdict
from datetime import datetime
from functools import lru_cache
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

from ecoproof.config import PROJECT_ROOT, Settings
from ecoproof.detect import evaluate
from ecoproof.transform.gold import read_silver_inputs


BEFORE = "450ed3dcc326c89d4d9b6406c374d3ab433fc8ffa7dd2c47d6ea978b8e809af1"
AFTER = "b4dbcd390245fb3147217e8237c0633a2407c484a648b37bd76a804d2eaf0982"
PERIODS = {
    "development": ("2026-10-03", "2026-10-05", "2026-10-12", 3, 42),
    "regression": ("2026-09-23", "2026-09-25", "2026-10-02", 5, 2026),
    "validation": ("2026-10-13", "2026-10-15", "2026-10-22", 5, 20261024),
}
PREVIOUS = {
    "development": "reports/history/2026-10-24-pre-plume/eval.json",
    "regression": "reports/detector-review/independent-after/eval.json",
}


def memoize_graph(module: ModuleType) -> None:
    """Reuse identical pure geometry calculations across intervention copies."""
    original = module.wind_weights

    @lru_cache(maxsize=512)
    def cached(points: tuple, options: tuple) -> tuple:
        return tuple(tuple(row) for row in original(points, **dict(options)))

    def weights(points: list, **options: float) -> tuple:
        return cached(tuple(tuple(point) for point in points), tuple(sorted(options.items())))

    module.wind_weights = weights


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--period", choices=PERIODS, required=True)
    parser.add_argument("--revision", choices=("before", "after"), required=True)
    args = parser.parse_args()
    source = PROJECT_ROOT / ("reports/history/2026-10-24-pre-plume/classifier.py"
                             if args.revision == "before" else "src/ecoproof/detect/classifier.py")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if source_hash != (BEFORE if args.revision == "before" else AFTER):
        raise SystemExit("Classifier differs from the frozen plume-review protocol")
    spec = importlib.util.spec_from_file_location("ecoproof_plume_review", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    memoize_graph(module)
    baseline, start, end, cases, seed = PERIODS[args.period]
    baseline, start, end = [datetime.fromisoformat(day + "T00:00:00+00:00") for day in (baseline, start, end)]
    stations, readings, weather, raw = read_silver_inputs(Settings(data_dir=args.data_dir.resolve()), "delhi", baseline, end)
    detector = module.DetectorConfig(sigma_km=10, alpha=0.5)
    config = evaluate.EvaluationConfig(cases_per_type=cases, seed=seed)
    if args.revision == "before" and args.period in PREVIOUS:
        previous = PREVIOUS[args.period]
        report = json.loads((PROJECT_ROOT / previous).read_text(encoding="utf-8"))
        if (report["input_fingerprint_sha256"] != evaluate._fingerprint(stations, readings, weather)
                or report["detector_config"] != asdict(detector)
                or report["evaluation_config"] != asdict(config)
                or report.get("detector_source_sha256") != BEFORE):
            raise SystemExit("Previous measured baseline does not match the frozen inputs/source/config")
        report["measurement_reused_from"] = previous
    else:
        evaluate.classify = module.classify
        report = evaluate.evaluate_dataset(stations, readings, weather, baseline_start=baseline,
                                          baseline_end=start, start=start, end=end, detector=detector,
                                          config=config, input_kind="silver_observations")
    report.update({"region_id": "delhi", "raw_input_rows_with_context": raw,
                   "review_period": args.period, "detector_revision": args.revision,
                   "detector_source_sha256": source_hash, "protocol": "docs/PLUME_REVIEW.md"})
    path, chart = evaluate.save_report(report, PROJECT_ROOT / "reports/plume-review" / f"{args.period}-{args.revision}")
    controls = [case["plume_control"] for case in report["cases"] if case["kind"] == "plume"]
    print(json.dumps({"status": report["status"], "period": args.period, "revision": args.revision,
                      "report": str(path), "chart": str(chart), "case_count": len(report["cases"]),
                      "plume_negative_control_passed": report["plume_negative_control_passed"],
                      "plume_false_faults": sum(row["ecoproof_faults_on_plume"] for row in controls),
                      "plume_affected": sum(row["affected_observations"] for row in controls),
                      "plume_low_confidence": sum(row["low_confidence_on_plume"] for row in controls),
                      "unchanged_fault_flags": report["unchanged_control"]["ecoproof"]["fp"],
                      "f1": {kind: group["methods"]["ecoproof"]["f1"] for kind, group in report["metrics"].items()}}, indent=2))
    if not report["plume_negative_control_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
