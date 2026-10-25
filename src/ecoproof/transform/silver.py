"""Rebuild validated Silver Parquet and DuckDB views from immutable Bronze."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import duckdb

from ecoproof.config import Settings
from ecoproof.transform.validation import (
    ReadingRow, RowRejected, StationRow, WeatherRow, identifier, number,
    object_value, reading_row, station_row, utc_timestamp, weather_row,
)


class BuildError(ValueError):
    """A complete, usable Silver build could not be published."""


@dataclass(frozen=True)
class Bronze:
    path: Path
    fetched_at: datetime
    kind: str
    request: dict[str, Any]
    response: dict[str, Any]
    sha256: str


@dataclass
class SilverData:
    stations: dict[str, StationRow] = field(default_factory=dict)
    sensors: dict[str, set[str]] = field(default_factory=dict)
    readings: dict[tuple[str, datetime, str], ReadingRow] = field(default_factory=dict)
    weather: dict[tuple[str, datetime], WeatherRow] = field(default_factory=dict)
    duplicates: Counter[str] = field(default_factory=Counter)
    outside_window: Counter[str] = field(default_factory=Counter)
    rejected: list[dict[str, Any]] = field(default_factory=list)

    def reject(self, table: str, source: Bronze, index: int, reason: str) -> None:
        self.rejected.append({"table": table, "file": source.path.name, "row_index": index, "reason": reason})


def read_bronze(directory: Path) -> list[Bronze]:
    entries = []
    for path in sorted(directory.glob("*.json")):
        try:
            content = path.read_bytes()
            doc = object_value(json.loads(content), "Bronze document")
            if doc.get("schema_version") != 1:
                raise RowRejected("unsupported Bronze schema_version")
            fetched_at = utc_timestamp(doc.get("fetched_at"))
            request = object_value(doc.get("request"), "request")
            object_value(request.get("params"), "request.params")
            object_value(request.get("context"), "request.context")
            response = object_value(doc.get("response"), "response")
            url = urlsplit(request.get("url", ""))
            if doc.get("source") == "openaq" and url.hostname == "api.openaq.org":
                kind = "stations" if url.path == "/v3/locations" else "readings"
                match = re.fullmatch(r"/v3/sensors/([1-9][0-9]*)/measurements", url.path)
                if kind == "readings" and (match is None or identifier(request["context"].get("sensor_id"), "sensor_id") != match[1]):
                    raise RowRejected("unsupported OpenAQ URL or mismatched sensor context")
                if not isinstance(response.get("results"), list):
                    raise RowRejected("missing OpenAQ results array")
            elif doc.get("source") == "openmeteo" and url.hostname == "archive-api.open-meteo.com" and url.path == "/v1/archive":
                kind = "weather"
            else:
                raise RowRejected("unsupported Bronze source/URL")
            entries.append(Bronze(path, fetched_at, kind, request, response, hashlib.sha256(content).hexdigest()))
        except (ValueError, TypeError, OSError) as exc:
            raise BuildError(f"Invalid Bronze file {path.name}: {exc}") from exc
    if not entries:
        raise BuildError("No Bronze JSON files found; ingest data before building Silver")
    return sorted(entries, key=lambda entry: (entry.fetched_at, entry.path.name))


def query_center(entry: Bronze) -> tuple[float, float]:
    params = entry.request["params"]
    try:
        if entry.kind == "stations":
            lat, lon = (float(part) for part in params["coordinates"].split(","))
            number(params.get("radius"), "radius", 1, 25000)
        else:
            lat, lon = params["latitude"], params["longitude"]
        return round(number(lat, "latitude", -90, 90), 4), round(number(lon, "longitude", -180, 180), 4)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise BuildError(f"Invalid request coordinates in {entry.path.name}") from exc


def select_region(entries: list[Bronze], region_id: str) -> tuple[list[Bronze], list[Bronze]]:
    weather = [entry for entry in entries if entry.kind == "weather" and entry.request["context"].get("region_id") == region_id]
    catalogs = [entry for entry in entries if entry.kind == "stations"]
    centers = {query_center(entry) for entry in weather}
    if centers:
        catalogs = [entry for entry in catalogs if query_center(entry) in centers]
    elif len({query_center(entry) for entry in catalogs}) > 1:
        raise BuildError("Ambiguous station regions: cache weather for the chosen region first")
    if not catalogs and not weather:
        raise BuildError("No catalog or weather data matches the requested region")
    return catalogs, weather


def _in_window(ts: datetime, start: datetime | None, end: datetime | None) -> bool:
    return (start is None or ts >= start) and (end is None or ts < end)


def collect_stations(catalogs: list[Bronze], region_id: str, data: SilverData) -> set[str]:
    catalog_ids = set()
    for entry in catalogs:
        for index, raw in enumerate(entry.response["results"]):
            try:
                if isinstance(raw, dict):
                    catalog_ids.add(identifier(raw.get("id"), "station_id"))
                row, sensors = station_row(raw, region_id)
                key = row[0]
                data.duplicates["stations"] += int(key in data.stations)
                data.stations[key] = row
                data.sensors[key] = sensors
            except RowRejected as exc:
                data.reject("stations", entry, index, str(exc))
    return catalog_ids


def collect_readings(
    entries: list[Bronze], selected_ids: set[str], other_ids: set[str], data: SilverData,
    start: datetime | None, end: datetime | None,
) -> None:
    for entry in entries:
        if entry.kind != "readings":
            continue
        context = entry.request["context"]
        try:
            station_id = identifier(context.get("location_id"), "location_id")
            sensor_id = identifier(context.get("sensor_id"), "sensor_id")
        except RowRejected as exc:
            raise BuildError(f"Invalid reading context in {entry.path.name}: {exc}") from exc
        if station_id in other_ids and station_id not in selected_ids:
            continue
        for index, raw in enumerate(entry.response["results"]):
            try:
                if station_id not in data.stations:
                    raise RowRejected("station_id: no valid matching station")
                if sensor_id not in data.sensors[station_id]:
                    raise RowRejected("sensor_id: not a PM2.5 sensor of this station")
                row = reading_row(raw, station_id)
                if not _in_window(row[1], start, end):
                    data.outside_window["readings"] += 1
                    continue
                key = row[:3]
                data.duplicates["readings"] += int(key in data.readings)
                data.readings[key] = row
            except RowRejected as exc:
                data.reject("readings", entry, index, str(exc))


WEATHER_UNITS = {"time": "iso8601", "wind_speed_10m": "m/s", "wind_direction_10m": "°",
                 "temperature_2m": "°C", "surface_pressure": "hPa"}


def collect_weather(
    entries: list[Bronze], region_id: str, data: SilverData,
    start: datetime | None, end: datetime | None,
) -> None:
    for entry in entries:
        response = entry.response
        hourly = response.get("hourly")
        if response.get("utc_offset_seconds") != 0:
            raise BuildError(f"Weather timezone is not UTC in {entry.path.name}")
        units = response.get("hourly_units")
        if not isinstance(units, dict) or any(units.get(key) != unit for key, unit in WEATHER_UNITS.items()):
            raise BuildError(f"Unsupported or missing weather units in {entry.path.name}")
        if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
            raise BuildError(f"Missing weather arrays in {entry.path.name}")
        size = len(hourly["time"])
        if any(not isinstance(hourly.get(key), list) or len(hourly[key]) != size for key in WEATHER_UNITS):
            raise BuildError(f"Weather array lengths do not match in {entry.path.name}")
        for index in range(size):
            try:
                row = weather_row(hourly, index, region_id)
                if not _in_window(row[1], start, end):
                    data.outside_window["weather"] += 1
                    continue
                key = row[:2]
                data.duplicates["weather"] += int(key in data.weather)
                data.weather[key] = row
            except RowRejected as exc:
                data.reject("weather", entry, index, str(exc))


def create_tables(db: duckdb.DuckDBPyConnection) -> None:
    """Enforce constraints before writing Parquet; published datasets are views."""
    db.execute("""
        CREATE TABLE stations (
            station_id TEXT PRIMARY KEY, name TEXT,
            lat DOUBLE NOT NULL CHECK (isfinite(lat) AND lat BETWEEN -90 AND 90),
            lon DOUBLE NOT NULL CHECK (isfinite(lon) AND lon BETWEEN -180 AND 180),
            provider TEXT, cluster_id TEXT NOT NULL);
        CREATE TABLE readings (
            station_id TEXT REFERENCES stations(station_id), ts TIMESTAMP NOT NULL,
            parameter TEXT NOT NULL CHECK (parameter = 'pm25'),
            value DOUBLE NOT NULL CHECK (isfinite(value) AND value BETWEEN 0 AND 1500),
            unit TEXT NOT NULL CHECK (unit = 'µg/m³'),
            PRIMARY KEY (station_id, ts, parameter));
        CREATE TABLE weather (
            region_id TEXT NOT NULL, ts TIMESTAMP NOT NULL,
            wind_speed DOUBLE NOT NULL CHECK (isfinite(wind_speed) AND wind_speed >= 0),
            wind_dir_deg DOUBLE NOT NULL CHECK (isfinite(wind_dir_deg) AND wind_dir_deg >= 0 AND wind_dir_deg < 360),
            temp DOUBLE NOT NULL CHECK (isfinite(temp)),
            pressure DOUBLE NOT NULL CHECK (isfinite(pressure) AND pressure > 0),
            PRIMARY KEY (region_id, ts));
    """)


TABLES = {"stations": (6, "station_id"), "readings": (5, "station_id, ts, parameter"),
          "weather": (6, "region_id, ts")}


def publish_views(database: Path, build_dir: Path) -> None:
    with duckdb.connect(str(database)) as db:
        db.execute("BEGIN TRANSACTION")
        try:
            db.execute("CREATE SCHEMA IF NOT EXISTS silver")
            for name in TABLES:
                # Identifiers are fixed above; SQL literals escape apostrophes in local paths.
                path = str((build_dir / f"{name}.parquet").resolve()).replace("'", "''")
                db.execute(f"CREATE OR REPLACE VIEW silver.{name} AS SELECT * FROM read_parquet('{path}')")
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise


def build_silver(
    settings: Settings, *, region_id: str, start_date: date | None = None, end_date: date | None = None,
) -> dict[str, Any]:
    if not region_id.strip():
        raise BuildError("region_id must not be blank")
    if (start_date is None) != (end_date is None) or (start_date and end_date and start_date > end_date):
        raise BuildError("Provide both dates in ascending order, or omit both")
    start = datetime.combine(start_date, time.min) if start_date else None
    end = datetime.combine(end_date + timedelta(days=1), time.min) if end_date else None
    entries = read_bronze(settings.bronze_dir)
    catalogs, weather = select_region(entries, region_id)
    data = SilverData()
    selected_ids = collect_stations(catalogs, region_id, data)
    other_ids = {str(row.get("id")) for entry in entries if entry.kind == "stations" and entry not in catalogs
                 for row in entry.response["results"] if isinstance(row, dict)}
    collect_readings(entries, selected_ids, other_ids, data, start, end)
    collect_weather(weather, region_id, data, start, end)
    if not data.stations and not data.readings and not data.weather:
        raise BuildError(f"No valid Silver rows remain ({len(data.rejected)} rejected); previous build is unchanged")
    with duckdb.connect() as db:
        create_tables(db)
        # Keep constraint validation, but avoid committing once per input row.
        db.execute("BEGIN TRANSACTION")
        for name, (width, _) in TABLES.items():
            rows = getattr(data, name)
            if rows:
                db.executemany(f"INSERT INTO {name} VALUES ({','.join('?' for _ in range(width))})", list(rows.values()))
        db.execute("COMMIT")
        coverage = db.execute("""
            SELECT station_id, count(*) AS readings, count(DISTINCT CAST(ts AS DATE)) AS utc_dates,
                   min(ts), max(ts) FROM readings GROUP BY station_id ORDER BY station_id
        """).fetchall()
        settings.silver_dir.mkdir(parents=True, exist_ok=True)
        build_dir = (settings.silver_dir / f"build-{uuid4().hex}").resolve()
        # These are persistent workspace outputs, not private OS temporary files.
        build_dir.mkdir()
        for name, (_, order) in TABLES.items():
            db.sql(f"SELECT * FROM {name} ORDER BY {order}").write_parquet(str(build_dir / f"{name}.parquet"), compression="zstd")
    warnings = []
    if sum(row[2] >= 7 for row in coverage) < 8:
        warnings.append("Fewer than 8 stations have valid readings on 7 UTC dates; the air-data milestone is not met.")
    if not data.weather:
        warnings.append("No valid weather rows are available for this region/window.")
    report = {
        "region_id": region_id, "counts": {name: len(getattr(data, name)) for name in TABLES},
        "duplicate_rows": dict(data.duplicates), "outside_window": dict(data.outside_window),
        "rejected_rows": len(data.rejected), "rejections": data.rejected,
        "window_start_utc": start.isoformat() + "Z" if start else None,
        "window_end_exclusive_utc": end.isoformat() + "Z" if end else None,
        "station_coverage": [{"station_id": row[0], "readings": row[1], "distinct_utc_dates": row[2],
                              "first_ts": row[3].isoformat() + "Z", "last_ts": row[4].isoformat() + "Z"} for row in coverage],
        "warnings": warnings, "build_dir": str(build_dir), "database": str(settings.duckdb_path.resolve()),
        "bronze_files": [{"file": entry.path.name, "sha256": entry.sha256} for entry in entries],
    }
    (build_dir / "build_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    # Files are complete before a single transaction switches all three public views.
    # Previous builds remain intact. Incomplete file sets are not referenced by the views.
    publish_views(settings.duckdb_path, build_dir)
    return report
