"""Offline Bronze-to-Silver build command."""

import argparse
from datetime import date
import json

import duckdb

from ecoproof.config import load_settings
from ecoproof.transform.silver import BuildError, build_silver


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild Silver Parquet and DuckDB views from local Bronze.")
    parser.add_argument("--region", required=True, help="Region ID matching the weather pull, e.g. delhi")
    parser.add_argument("--start-date", type=date.fromisoformat, help="First UTC date (inclusive)")
    parser.add_argument("--end-date", type=date.fromisoformat, help="Last UTC date (inclusive)")
    args = parser.parse_args()
    try:
        report = build_silver(load_settings(), region_id=args.region, start_date=args.start_date, end_date=args.end_date)
    except (BuildError, OSError, duckdb.Error) as exc:
        raise SystemExit(str(exc)) from None
    summary = {key: value for key, value in report.items() if key not in ("rejections", "bronze_files")}
    summary["report"] = str(report["build_dir"]) + "/build_report.json"
    print(json.dumps(summary, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
