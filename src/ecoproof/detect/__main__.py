"""Offline Silver-to-Gold classification command."""

import argparse
from datetime import datetime
import json

import duckdb

from ecoproof.config import load_settings
from ecoproof.detect.classifier import DetectorConfig, utc_hour
from ecoproof.transform.gold import build_classifications
from ecoproof.transform.silver import build_silver


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify hourly Silver PM2.5 using an earlier presumed-healthy baseline.")
    parser.add_argument("--region", required=True)
    parser.add_argument("--rebuild-silver", action="store_true",
                        help="Rebuild Silver from local Bronze before classification (no network)")
    for name in ("baseline-start", "baseline-end", "start", "end"):
        parser.add_argument(f"--{name}", required=True, type=datetime.fromisoformat,
                            help="ISO timestamp with timezone on a UTC hour; end bounds are exclusive")
    parser.add_argument("--sigma-km", required=True, type=float)
    parser.add_argument("--alpha", required=True, type=float)
    parser.add_argument("--tau-km", type=float, default=20.0)
    parser.add_argument("--z-threshold", type=float, default=2.5)
    parser.add_argument("--scale-floor", type=float, default=1.0, help="Provisional residual noise floor in micrograms/m³")
    parser.add_argument("--min-baseline-samples", type=int, default=24)
    args = parser.parse_args()
    try:
        config = DetectorConfig(sigma_km=args.sigma_km, alpha=args.alpha, tau_km=args.tau_km,
                                z_threshold=args.z_threshold, scale_floor=args.scale_floor,
                                min_baseline_samples=args.min_baseline_samples)
        bounds = tuple(map(utc_hour, (args.baseline_start, args.baseline_end, args.start, args.end)))
        if not bounds[0] < bounds[1] <= bounds[2] < bounds[3]:
            raise ValueError("Require baseline_start < baseline_end <= start < end")
        settings = load_settings()
        if args.rebuild_silver:
            build_silver(settings, region_id=args.region)
        report = build_classifications(settings, region_id=args.region, baseline_start=args.baseline_start,
                                       baseline_end=args.baseline_end, start=args.start, end=args.end, config=config)
    except (ValueError, OSError, duckdb.Error) as exc:
        raise SystemExit(str(exc)) from None
    summary = {key: value for key, value in report.items() if key not in ("baselines", "station_coverage")}
    summary["report"] = str(report["build_dir"]) + "/build_report.json"
    print(json.dumps(summary, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
