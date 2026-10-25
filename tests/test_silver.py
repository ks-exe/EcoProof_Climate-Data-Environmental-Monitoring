"""Synthetic provider-shaped fixtures exercise the actual offline Silver build."""

from collections.abc import Callable
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

import duckdb
import pytest

from ecoproof.config import Settings
from ecoproof.transform.silver import BuildError, build_silver, create_tables, publish_views
from ecoproof.transform.validation import RowRejected, reading_row, station_row


def station(station_id: int = 1) -> dict[str, Any]:
    return {"id": station_id, "name": "Synthetic station", "isMobile": False,
            "coordinates": {"latitude": 28.6, "longitude": 77.2},
            "provider": {"name": "Synthetic test provider"},
            "sensors": [{"id": station_id * 10, "parameter": {"id": 2, "name": "pm25", "units": "µg/m³"}}]}


def reading(value: Any = 12.5, ts: str = "2026-10-05T00:00:00Z") -> dict[str, Any]:
    return {"value": value, "parameter": {"id": 2, "name": "pm25", "units": "µg/m³"},
            "period": {"datetimeTo": {"utc": ts}, "interval": "01:00:00"}}


def weather() -> dict[str, Any]:
    return {"utc_offset_seconds": 0,
            "hourly_units": {"time": "iso8601", "wind_speed_10m": "m/s", "wind_direction_10m": "°",
                             "temperature_2m": "°C", "surface_pressure": "hPa"},
            "hourly": {"time": ["2026-10-05T00:00", "2026-10-05T01:00", "2026-10-05T02:00"],
                       "wind_speed_10m": [0, 2, 3], "wind_direction_10m": [360, 180, 90],
                       "temperature_2m": [-5, 20, 21], "surface_pressure": [1000, 1001, 1002]}}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(tmp_path / "data's folder")


@pytest.fixture
def bronze(settings: Settings) -> Callable[..., Path]:
    counter = 0

    def write(kind: str, response: Any, *, fetched_at: str = "2026-10-19T10:00:00Z",
              location_id: int = 1, region: str = "test", center: tuple[float, float] = (28.6139, 77.209),
              context: dict[str, Any] | None = None) -> Path:
        nonlocal counter
        counter += 1
        source = "openmeteo" if kind == "weather" else "openaq"
        if kind == "stations":
            request = {"url": "https://api.openaq.org/v3/locations", "context": {},
                       "params": {"coordinates": f"{center[0]:.4f},{center[1]:.4f}", "radius": 25000}}
            payload = {"results": response}
        elif kind == "readings":
            request = {"url": f"https://api.openaq.org/v3/sensors/{location_id * 10}/measurements",
                       "context": {"location_id": location_id, "sensor_id": location_id * 10},
                       "params": {"datetime_from": "2026-10-05T00:00:00Z", "datetime_to": "2026-10-06T00:00:00Z"}}
            payload = {"results": response}
        else:
            request = {"url": "https://archive-api.open-meteo.com/v1/archive", "context": {"region_id": region},
                       "params": {"latitude": center[0], "longitude": center[1]}}
            payload = response
        if context is not None:
            request["context"] = context
        settings.bronze_dir.mkdir(parents=True, exist_ok=True)
        path = settings.bronze_dir / f"{source}_{counter:03d}.json"
        path.write_text(json.dumps({"schema_version": 1, "source": source, "fetched_at": fetched_at,
                                    "request": request, "response": payload}), encoding="utf-8")
        return path

    return write


def query(settings: Settings, sql: str) -> list[tuple[Any, ...]]:
    with duckdb.connect(str(settings.duckdb_path), read_only=True) as db:
        return db.execute(sql).fetchall()


@pytest.mark.parametrize("value", [-0.01, 1500.01, None, float("nan"), float("inf"), float("-inf"), True, "12"])
def test_invalid_pm25_values_are_rejected(value: Any) -> None:
    with pytest.raises(RowRejected, match="value"):
        reading_row(reading(value), "1")


@pytest.mark.parametrize("value", [0, 1500])
def test_pm25_bounds_are_inclusive(value: float) -> None:
    assert reading_row(reading(value), "1")[3] == value


@pytest.mark.parametrize("unit", ["µg/m³", "μg/m³", "ug/m3", "µg/m3"])
def test_equivalent_mass_unit_spellings_are_normalized(unit: str) -> None:
    row = reading()
    row["parameter"]["units"] = unit
    assert reading_row(row, "1")[4] == "µg/m³"


@pytest.mark.parametrize("field,value", [("units", "ppm"), ("id", 1), ("name", "pm10")])
def test_wrong_pollutant_or_units_are_rejected(field: str, value: Any) -> None:
    row = reading()
    row["parameter"][field] = value
    with pytest.raises(RowRejected):
        reading_row(row, "1")


@pytest.mark.parametrize("ts", ["2026-10-05T00:00:00", "2026-10-05", "invalid", None])
def test_openaq_requires_an_explicit_timestamp_timezone(ts: Any) -> None:
    with pytest.raises(RowRejected, match="ts"):
        reading_row(reading(ts=ts), "1")


def test_openaq_offset_is_normalized_without_shifting_interval_end() -> None:
    result = reading_row(reading(ts="2026-10-05T05:30:00+05:30"), "1")
    assert result[1] == datetime(2026, 10, 5)
    assert result[1].tzinfo is None


@pytest.mark.parametrize("field,value", [("latitude", 91), ("longitude", -181), ("latitude", None),
                                         ("longitude", float("nan")), ("latitude", True)])
def test_invalid_station_coordinates_are_rejected(field: str, value: Any) -> None:
    row = station()
    row["coordinates"][field] = value
    with pytest.raises(RowRejected):
        station_row(row, "test")


def test_mobile_station_and_missing_pm25_sensor_are_rejected() -> None:
    row = station()
    row["isMobile"] = True
    with pytest.raises(RowRejected, match="stationary"):
        station_row(row, "test")
    row["isMobile"] = False
    row["sensors"] = []
    with pytest.raises(RowRejected, match="PM2.5"):
        station_row(row, "test")


def test_full_build_parquet_views_schema_and_bronze_immutability(settings: Settings, bronze: Callable[..., Path]) -> None:
    files = [bronze("stations", [station()]), bronze("readings", [reading()]), bronze("weather", weather())]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    report = build_silver(settings, region_id="test")
    assert report["counts"] == {"stations": 1, "readings": 1, "weather": 3}
    assert report["rejected_rows"] == 0
    assert query(settings, "SELECT station_id, parameter, value, unit, ts FROM silver.readings") == [
        ("1", "pm25", 12.5, "µg/m³", datetime(2026, 10, 5))]
    assert query(settings, "SELECT wind_speed, wind_dir_deg, temp FROM silver.weather ORDER BY ts")[0] == (0.0, 0.0, -5.0)
    assert query(settings, "SELECT cluster_id FROM silver.stations") == [("test",)]
    schema = query(settings, "DESCRIBE silver.readings")
    assert [(column[0], column[1]) for column in schema] == [
        ("station_id", "VARCHAR"), ("ts", "TIMESTAMP"), ("parameter", "VARCHAR"), ("value", "DOUBLE"), ("unit", "VARCHAR")]
    for name in ("stations", "readings", "weather"):
        path = Path(report["build_dir"]) / f"{name}.parquet"
        assert path.read_bytes()[:4] == b"PAR1"
        with duckdb.connect() as db:
            assert db.read_parquet(str(path)).count("*").fetchone()[0] == report["counts"][name]
    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in files} == before


def test_dedupe_uses_latest_valid_pull_and_normalized_utc_key(settings: Settings, bronze: Callable[..., Path]) -> None:
    bronze("stations", [station()])
    bronze("readings", [reading(25, "2026-10-05T05:00:00+05:00")], fetched_at="2026-10-19T12:00:00Z")
    bronze("readings", [reading(10)], fetched_at="2026-10-19T11:00:00Z")  # later filename, earlier fetch
    bronze("readings", [reading(2000)], fetched_at="2026-10-19T13:00:00Z")
    report = build_silver(settings, region_id="test")
    assert query(settings, "SELECT value FROM silver.readings") == [(25.0,)]
    assert report["duplicate_rows"]["readings"] == 1
    assert report["rejected_rows"] == 1


def test_duplicate_metadata_weather_and_readings_within_a_pull(settings: Settings, bronze: Callable[..., Path]) -> None:
    bronze("stations", [station(), {**station(), "name": "Latest valid test name"}])
    bronze("readings", [reading(1), reading(2)])
    bronze("weather", weather())
    updated = weather()
    updated["hourly"]["wind_speed_10m"][0] = 9
    bronze("weather", updated, fetched_at="2026-10-19T11:00:00Z")
    report = build_silver(settings, region_id="test")
    assert report["duplicate_rows"] == {"stations": 1, "readings": 1, "weather": 3}
    assert query(settings, "SELECT name FROM silver.stations") == [("Latest valid test name",)]
    assert query(settings, "SELECT value FROM silver.readings") == [(2.0,)]
    assert query(settings, "SELECT wind_speed FROM silver.weather ORDER BY ts")[0] == (9.0,)


def test_invalid_rows_are_excluded_with_traceable_reasons(settings: Settings, bronze: Callable[..., Path]) -> None:
    bad_station = station(2)
    bad_station["coordinates"]["latitude"] = 100
    bronze("stations", [station(), bad_station])
    bad_file = bronze("readings", [reading(-1), reading(1501), reading(None), reading(0), reading(1500)])
    bronze("readings", [reading()], location_id=2)
    bronze("readings", [reading()], location_id=99)
    report = build_silver(settings, region_id="test")
    assert report["counts"]["stations"] == 1
    assert report["rejected_rows"] == 6
    assert len([item for item in report["rejections"] if item["file"] == bad_file.name]) == 3
    assert all("row_index" in item and item["reason"] for item in report["rejections"])
    assert query(settings, "SELECT value FROM silver.readings") == [(1500.0,)]


@pytest.mark.parametrize("key,value", [("wind_speed_10m", -1), ("wind_speed_10m", None),
                                      ("wind_direction_10m", 361), ("temperature_2m", float("nan")),
                                      ("surface_pressure", 0), ("surface_pressure", None)])
def test_invalid_weather_rows_are_excluded(
    key: str, value: Any, settings: Settings, bronze: Callable[..., Path],
) -> None:
    payload = weather()
    payload["hourly"][key][0] = value
    bronze("weather", payload)
    report = build_silver(settings, region_id="test")
    assert report["counts"]["weather"] == 2
    assert report["rejected_rows"] == 1
    assert report["rejections"][0]["table"] == "weather"


def test_explicit_date_window_is_half_open_in_utc(settings: Settings, bronze: Callable[..., Path]) -> None:
    bronze("stations", [station()])
    bronze("readings", [reading(1, "2026-10-04T23:59:59Z"), reading(2), reading(3, "2026-10-06T00:00:00Z")])
    bronze("weather", weather())
    report = build_silver(settings, region_id="test", start_date=date(2026, 10, 5), end_date=date(2026, 10, 5))
    assert query(settings, "SELECT value FROM silver.readings") == [(2.0,)]
    assert report["outside_window"]["readings"] == 2
    assert report["window_end_exclusive_utc"] == "2026-10-06T00:00:00Z"


def test_partial_weather_only_build_reports_empty_air_tables(settings: Settings, bronze: Callable[..., Path]) -> None:
    bronze("weather", weather())
    report = build_silver(settings, region_id="test")
    assert report["counts"] == {"stations": 0, "readings": 0, "weather": 3}
    assert query(settings, "SELECT count(*) FROM silver.readings") == [(0,)]
    assert report["warnings"] and report["station_coverage"] == []


def test_regions_are_not_silently_combined(settings: Settings, bronze: Callable[..., Path]) -> None:
    bronze("weather", weather(), region="test")
    bronze("weather", weather(), region="elsewhere", center=(0, 0))
    bronze("stations", [station()])
    bronze("stations", [station(2)], center=(0, 0))
    bronze("readings", [reading()], location_id=1)
    bronze("readings", [reading()], location_id=2)
    report = build_silver(settings, region_id="test")
    assert report["counts"] == {"stations": 1, "readings": 1, "weather": 3}
    assert report["rejected_rows"] == 0


def test_rebuild_is_deterministic_and_keeps_prior_outputs(settings: Settings, bronze: Callable[..., Path]) -> None:
    bronze("stations", [station()])
    bronze("readings", [reading()])
    bronze("weather", weather())
    first = build_silver(settings, region_id="test")
    old_files = {path: path.read_bytes() for path in Path(first["build_dir"]).glob("*.parquet")}
    before = query(settings, "SELECT * FROM silver.readings")
    second = build_silver(settings, region_id="test")
    assert first["build_dir"] != second["build_dir"]
    assert first["counts"] == second["counts"]
    assert first["station_coverage"] == second["station_coverage"]
    assert query(settings, "SELECT * FROM silver.readings") == before
    assert all(path.read_bytes() == content for path, content in old_files.items())


@pytest.mark.parametrize("change", ["units", "timezone", "arrays", "json"])
def test_malformed_input_preserves_previous_published_build(
    change: str, settings: Settings, bronze: Callable[..., Path],
) -> None:
    bronze("weather", weather())
    first = build_silver(settings, region_id="test")
    before = query(settings, "SELECT * FROM silver.weather ORDER BY ts")
    payload = weather()
    if change == "units":
        payload["hourly_units"]["wind_speed_10m"] = "km/h"
    elif change == "timezone":
        payload["utc_offset_seconds"] = 18000
    elif change == "arrays":
        payload["hourly"]["wind_speed_10m"] = [1]
    path = bronze("weather", payload)
    if change == "json":
        path.write_text("not json", encoding="utf-8")
    with pytest.raises(BuildError):
        build_silver(settings, region_id="test")
    assert query(settings, "SELECT * FROM silver.weather ORDER BY ts") == before
    assert Path(first["build_dir"]).exists()


def test_view_publication_rolls_back_all_views_if_one_file_is_missing(
    settings: Settings, bronze: Callable[..., Path], tmp_path: Path,
) -> None:
    bronze("weather", weather())
    first = build_silver(settings, region_id="test")
    before = query(settings, "SELECT view_name, sql FROM duckdb_views() WHERE schema_name = 'silver' ORDER BY view_name")
    broken = tmp_path / "incomplete-build"
    broken.mkdir()
    for name in ("stations", "readings"):
        shutil.copyfile(Path(first["build_dir"]) / f"{name}.parquet", broken / f"{name}.parquet")
    with pytest.raises(duckdb.Error):
        publish_views(settings.duckdb_path, broken)
    after = query(settings, "SELECT view_name, sql FROM duckdb_views() WHERE schema_name = 'silver' ORDER BY view_name")
    assert after == before
    assert query(settings, "SELECT count(*) FROM silver.weather") == [(3,)]


def test_no_input_does_not_create_a_database(settings: Settings) -> None:
    with pytest.raises(BuildError, match="No Bronze"):
        build_silver(settings, region_id="test")
    assert not settings.duckdb_path.exists()


@pytest.mark.parametrize("invalid", [-1, 1501, None, float("nan"), float("inf")])
def test_duckdb_itself_rejects_reading_constraint_violations(invalid: Any) -> None:
    with duckdb.connect() as db:
        create_tables(db)
        db.execute("INSERT INTO stations VALUES ('1', 'Synthetic', 0, 0, 'Test', 'test')")
        with pytest.raises(duckdb.ConstraintException):
            db.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", ["1", datetime(2026, 10, 5), "pm25", invalid, "µg/m³"])


def test_duckdb_enforces_primary_and_foreign_keys() -> None:
    with duckdb.connect() as db:
        create_tables(db)
        db.execute("INSERT INTO stations VALUES ('1', 'Synthetic', 0, 0, 'Test', 'test')")
        values = ["1", datetime(2026, 10, 5), "pm25", 10, "µg/m³"]
        db.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", values)
        with pytest.raises(duckdb.ConstraintException):
            db.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", values)
        with pytest.raises(duckdb.ConstraintException):
            db.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", ["999", *values[1:]])
