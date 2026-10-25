"""Reproduce the fixed before/after experiment in docs/DETECTOR_REVIEW.md.

This offline script reads Silver and writes reports only. The archived source is
part of the experiment; it is never loaded by the API or the production detector.
"""

import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from ecoproof.config import PROJECT_ROOT, Settings
from ecoproof.detect import evaluate
from ecoproof.transform.gold import read_silver_inputs


ORIGINAL_SHA256 = "ff345864804e7e1ef977e1645c56a0f9ada0c4b2b3d6c9a1f0b9da508d76eca3"
FLATLINE_SHA256 = "450ed3dcc326c89d4d9b6406c374d3ab433fc8ffa7dd2c47d6ea978b8e809af1"
PERIODS = {
    "development": ("2026-10-03", "2026-10-05", "2026-10-12", 3, 42),
    "independent": ("2026-09-23", "2026-09-25", "2026-10-02", 5, 2026),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--period", choices=PERIODS, required=True)
    parser.add_argument("--revision", choices=("before", "after"), required=True)
    args = parser.parse_args()
    # Both revisions are pinned: later application fixes must not silently
    # change the October 23 comparison when its commands are repeated.
    source = PROJECT_ROOT / ("reports/history/2026-10-23-initial/classifier.py"
                             if args.revision == "before" else "reports/history/2026-10-24-pre-plume/classifier.py")
    expected = ORIGINAL_SHA256 if args.revision == "before" else FLATLINE_SHA256
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
        raise SystemExit("Archived classifier differs from the fixed protocol")
    spec = importlib.util.spec_from_file_location("ecoproof_review_original", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    baseline, start, end, cases, seed = PERIODS[args.period]
    baseline, start, end = [datetime.fromisoformat(day + "T00:00:00+00:00") for day in (baseline, start, end)]
    stations, readings, weather, raw_count = read_silver_inputs(
        Settings(data_dir=args.data_dir.resolve()), "delhi", baseline, end,
    )
    # Both revisions use the same evaluator, geometry-based case selection and
    # interventions. Only the classifier callable changes in this isolated process.
    evaluate.classify = module.classify
    report = evaluate.evaluate_dataset(
        stations, readings, weather, baseline_start=baseline, baseline_end=start,
        start=start, end=end, detector=module.DetectorConfig(sigma_km=10, alpha=0.5),
        config=evaluate.EvaluationConfig(cases_per_type=cases, seed=seed),
        input_kind="silver_observations",
    )
    report.update({
        "region_id": "delhi", "raw_input_rows_with_context": raw_count,
        "review_period": args.period, "detector_revision": args.revision,
        "detector_source_sha256": source_hash, "protocol": "docs/DETECTOR_REVIEW.md",
    })
    directory = PROJECT_ROOT / "reports/detector-review" / f"{args.period}-{args.revision}"
    path, chart = evaluate.save_report(report, directory)
    print(json.dumps({
        "status": report["status"], "period": args.period, "revision": args.revision,
        "report": str(path), "chart": str(chart), "case_count": len(report["cases"]),
        "plume_negative_control_passed": report["plume_negative_control_passed"],
        "unchanged_fault_flags": report["unchanged_control"]["ecoproof"]["fp"],
        "f1": {kind: group["methods"]["ecoproof"]["f1"] for kind, group in report["metrics"].items()},
    }, indent=2))
    if not report["plume_negative_control_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
