"""Materialize classifications with canonical hashes and matching batch links."""

from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from statistics import fmean
from typing import Any
from uuid import uuid4

import duckdb

from ecoproof.config import Settings
from ecoproof.detect.classifier import DetectorConfig, DetectionRun, classify, utc_hour
from ecoproof.provenance.batches import classification_payload, publish_classified_view
from ecoproof.provenance.merkle import hash_record
from ecoproof.transform.validation import PM25_UNIT, number


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def hourly_readings(rows: list[tuple[str, datetime, float, str]]) -> dict[tuple[str, datetime], float]:
    """Mean samples ending in (H-1h, H], without filling empty hours.

    Silver's timezone-naive TIMESTAMP has a fixed UTC meaning. Aggregation uses
    sample means, not duration-weighted averages; the raw timestamps stay in Silver.
    """
    buckets = defaultdict(list)
    for station, ts, value, unit in rows:
        if unit != PM25_UNIT:
            raise ValueError("Silver readings must use micrograms per cubic meter")
        if ts.tzinfo is not None:
            raise ValueError("Silver TIMESTAMP must be timezone-naive UTC")
        hour = ts.replace(minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        if ts.minute or ts.second or ts.microsecond:
            hour += timedelta(hours=1)
        buckets[station, hour].append(number(value, "PM2.5", 0, 1500))
    return {key: fmean(values) for key, values in sorted(buckets.items())}


def read_silver_inputs(
    settings: Settings, region_id: str, baseline_start: datetime, end: datetime,
) -> tuple[dict, dict, dict, int]:
    """Read one regional Silver snapshot and return hourly inputs without writes."""
    with duckdb.connect(str(settings.duckdb_path), read_only=True) as db:
        db.execute("BEGIN TRANSACTION")
        stations = db.execute(
            "SELECT station_id, lat, lon FROM silver.stations WHERE cluster_id = ? ORDER BY station_id",
            [region_id],
        ).fetchall()
        if not stations:
            raise ValueError(f"No Silver stations for region '{region_id}'; ingest OpenAQ and rebuild Silver first")
        # Read one snapshot, including prior baseline and later plume context.
        lower = (baseline_start - timedelta(hours=1)).replace(tzinfo=None)
        upper = (end + timedelta(hours=3)).replace(tzinfo=None)
        raw = db.execute("""
            SELECT r.station_id, r.ts, r.value, r.unit FROM silver.readings r
            JOIN silver.stations s ON r.station_id = s.station_id
            WHERE s.cluster_id = ? AND r.parameter = 'pm25' AND r.ts > ? AND r.ts < ?
            ORDER BY r.station_id, r.ts
        """, [region_id, lower, upper]).fetchall()
        weather = db.execute("""
            SELECT ts, wind_speed, wind_dir_deg FROM silver.weather
            WHERE region_id = ? AND ts >= ? AND ts < ? ORDER BY ts
        """, [region_id, baseline_start.replace(tzinfo=None), upper]).fetchall()
        db.execute("COMMIT")
    points = {station: (lat, lon) for station, lat, lon in stations}
    winds = {ts.replace(tzinfo=timezone.utc): (speed, direction) for ts, speed, direction in weather}
    return points, hourly_readings(raw), winds, len(raw)


def _write_parquet(run: DetectionRun, build_dir: Path) -> None:
    with duckdb.connect() as db:
        db.execute("""
            CREATE TABLE classified (
                station_id TEXT NOT NULL, ts TIMESTAMP NOT NULL,
                value DOUBLE NOT NULL CHECK (isfinite(value) AND value BETWEEN 0 AND 1500),
                expected DOUBLE CHECK (isfinite(expected)), residual DOUBLE CHECK (isfinite(residual)),
                z DOUBLE CHECK (isfinite(z) AND z >= 0),
                label TEXT NOT NULL CHECK (label IN ('VALID','SENSOR_FAULT_DRIFT','VERIFIED_PLUME_EVENT')),
                neighbor_count INTEGER NOT NULL CHECK (neighbor_count >= 0),
                wind_speed DOUBLE, wind_dir_deg DOUBLE, record_hash TEXT, batch_id TEXT,
                PRIMARY KEY (station_id, ts));
            CREATE TABLE classification_evidence (
                station_id TEXT NOT NULL, ts TIMESTAMP NOT NULL,
                low_confidence BOOLEAN NOT NULL, reason TEXT NOT NULL,
                baseline_sigma DOUBLE, smoothed_z DOUBLE, plume_evidence_json TEXT NOT NULL,
                plume_sources_json TEXT NOT NULL,
                PRIMARY KEY (station_id, ts));
        """)
        classified, evidence = [], []
        for record in run.records:
            ts = record.ts.replace(tzinfo=None)
            classified.append((record.station_id, ts, record.value, record.expected, record.residual,
                               record.z, record.label, record.neighbor_count, record.wind_speed,
                               record.wind_dir_deg, hash_record(classification_payload(record)).hex(), None))
            plume = [{**asdict(item), "ts": _iso(item.ts)} for item in record.plume_evidence]
            sources = [{"station_id": station, "ts": _iso(ts)} for station, ts in record.plume_sources]
            evidence.append((record.station_id, ts, record.low_confidence, record.reason,
                             record.baseline_sigma, record.smoothed_z, json.dumps(plume, allow_nan=False),
                             json.dumps(sources, allow_nan=False)))
        db.execute("BEGIN TRANSACTION")
        db.executemany("INSERT INTO classified VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", classified)
        db.executemany("INSERT INTO classification_evidence VALUES (?,?,?,?,?,?,?,?)", evidence)
        db.execute("COMMIT")
        for name in ("classified", "classification_evidence"):
            db.sql(f"SELECT * FROM {name} ORDER BY station_id, ts").write_parquet(
                str(build_dir / f"{name}.parquet"), compression="zstd"
            )


def publish_classifications(database: Path, build_dir: Path) -> None:
    """Switch data and confidence together; leave earlier builds and batches intact."""
    with duckdb.connect(str(database)) as db:
        db.execute("BEGIN TRANSACTION")
        try:
            db.execute("CREATE SCHEMA IF NOT EXISTS gold")
            for name in ("classified", "classification_evidence"):
                if name == "classified":
                    publish_classified_view(db, build_dir / "classified.parquet")
                    continue
                path = str((build_dir / f"{name}.parquet").resolve()).replace("'", "''")
                db.execute(f"CREATE OR REPLACE VIEW gold.{name} AS SELECT * FROM read_parquet('{path}')")
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise


def build_classifications(
    settings: Settings, *, region_id: str, baseline_start: datetime, baseline_end: datetime,
    start: datetime, end: datetime, config: DetectorConfig,
) -> dict[str, Any]:
    """Rebuild Gold from current Silver without network calls or invented readings."""
    if not region_id.strip():
        raise ValueError("region_id must not be blank")
    baseline_start, baseline_end, start, end = map(utc_hour, (baseline_start, baseline_end, start, end))
    if not baseline_start < baseline_end <= start < end:
        raise ValueError("Require baseline_start < baseline_end <= start < end")
    stations, readings, weather, raw_count = read_silver_inputs(settings, region_id, baseline_start, end)
    run = classify(stations, readings, weather, baseline_start=baseline_start, baseline_end=baseline_end,
                   start=start, end=end, config=config)
    if not run.records:
        raise ValueError("No Silver PM2.5 readings in the classification window; previous Gold is unchanged")
    warnings = []
    if any(record.low_confidence for record in run.records):
        warnings.append("Low-confidence VALID rows require their evidence flags; they are not verified healthy data.")
    coverage = Counter(record.station_id for record in run.records)
    dates = {station: {record.ts.date() for record in run.records if record.station_id == station}
             for station in coverage}
    if sum(len(days) >= 7 for days in dates.values()) < 8:
        warnings.append("Fewer than 8 stations have classified observations on 7 UTC dates; the real-data milestone is not established.")
    report = {
        "region_id": region_id, "baseline_start_utc": _iso(baseline_start),
        "baseline_end_exclusive_utc": _iso(baseline_end), "start_utc": _iso(start),
        "end_exclusive_utc": _iso(end), "config": asdict(config),
        "raw_readings_with_context": raw_count, "hourly_readings_with_context": len(readings),
        "classified_records": len(run.records), "labels": dict(Counter(row.label for row in run.records)),
        "low_confidence_records": sum(row.low_confidence for row in run.records),
        "reasons": dict(Counter(row.reason for row in run.records)),
        "baselines": {station: asdict(baseline) for station, baseline in run.baselines.items()},
        "station_coverage": [{"station_id": station, "hours_with_readings": count,
                              "distinct_utc_dates": len(dates[station])} for station, count in sorted(coverage.items())],
        "warnings": warnings,
        "interpretation": "Retrospective heuristic labels. Faults are suspected; plume labels are wind/neighbor evidence, not external verification.",
    }
    settings.gold_dir.mkdir(parents=True, exist_ok=True)
    build_dir = (settings.gold_dir / f"build-{uuid4().hex}").resolve()
    build_dir.mkdir()
    _write_parquet(run, build_dir)
    report["build_dir"] = str(build_dir)
    report["database"] = str(settings.duckdb_path.resolve())
    (build_dir / "build_report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    publish_classifications(settings.duckdb_path, build_dir)
    return report
