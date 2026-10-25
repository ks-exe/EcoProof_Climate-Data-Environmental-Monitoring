"""Validation and UTC normalization for the Silver schemas in SPEC section 4."""

from datetime import datetime, timezone
import math
from typing import Any


PM25_UNIT = "µg/m³"
StationRow = tuple[str, str | None, float, float, str | None, str]
ReadingRow = tuple[str, datetime, str, float, str]
WeatherRow = tuple[str, datetime, float, float, float, float]


class RowRejected(ValueError):
    """A row cannot be admitted to Silver; its Bronze source remains untouched."""


def object_value(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RowRejected(f"{field}: expected an object")
    return value


def identifier(value: Any, field: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise RowRejected(f"{field}: expected a positive integer ID")
    if not str(value).isascii() or not str(value).isdecimal() or int(value) <= 0:
        raise RowRejected(f"{field}: expected a positive integer ID")
    return str(int(value))


def number(value: Any, field: str, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RowRejected(f"{field}: expected a finite number")
    try:
        result = float(value)
    except OverflowError:
        raise RowRejected(f"{field}: expected a finite number") from None
    if not math.isfinite(result):
        raise RowRejected(f"{field}: expected a finite number")
    if minimum is not None and result < minimum or maximum is not None and result > maximum:
        raise RowRejected(f"{field}: outside allowed range")
    return result


def utc_timestamp(value: Any, *, assume_utc: bool = False) -> datetime:
    if not isinstance(value, str) or "T" not in value:
        raise RowRejected("ts: expected an ISO datetime")
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        raise RowRejected("ts: invalid ISO datetime") from None
    if result.utcoffset() is None:
        if not assume_utc:
            raise RowRejected("ts: timezone is required")
        result = result.replace(tzinfo=timezone.utc)
    # The spec uses TIMESTAMP, not TIMESTAMPTZ. Naive stored values ALWAYS mean UTC.
    return result.astimezone(timezone.utc).replace(tzinfo=None)


def optional_text(value: Any, field: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise RowRejected(f"{field}: expected text or null")


def station_row(raw: Any, region_id: str) -> tuple[StationRow, set[str]]:
    row = object_value(raw, "station")
    station_id = identifier(row.get("id"), "station_id")
    if row.get("isMobile") is not False:
        raise RowRejected("station: must be explicitly stationary")
    coordinates = object_value(row.get("coordinates"), "coordinates")
    lat = number(coordinates.get("latitude"), "lat", -90, 90)
    lon = number(coordinates.get("longitude"), "lon", -180, 180)
    if not isinstance(row.get("sensors"), list):
        raise RowRejected("station: missing sensor metadata")
    sensors = set()
    for raw_sensor in row["sensors"]:
        sensor = object_value(raw_sensor, "sensor")
        parameter = object_value(sensor.get("parameter"), "sensor.parameter")
        if parameter.get("id") == 2 and parameter.get("name") == "pm25":
            sensors.add(identifier(sensor.get("id"), "sensor_id"))
    if not sensors:
        raise RowRejected("station: no PM2.5 sensor")
    provider = object_value(row.get("provider") or {}, "provider")
    return (station_id, optional_text(row.get("name"), "name"), lat, lon,
            optional_text(provider.get("name"), "provider"), region_id), sensors


def reading_row(raw: Any, station_id: str) -> ReadingRow:
    row = object_value(raw, "reading")
    parameter = object_value(row.get("parameter"), "parameter")
    if parameter.get("id") != 2 or parameter.get("name") != "pm25":
        raise RowRejected("parameter: expected PM2.5 (id 2, pm25)")
    unit = parameter.get("units")
    if unit not in (PM25_UNIT, "μg/m³", "ug/m3", "µg/m3"):
        raise RowRejected("unit: expected micrograms per cubic meter")
    value = number(row.get("value"), "value", 0, 1500)
    period = object_value(row.get("period"), "period")
    ending = object_value(period.get("datetimeTo"), "period.datetimeTo")
    ts = utc_timestamp(ending.get("utc"))
    return station_id, ts, "pm25", value, PM25_UNIT


def weather_row(hourly: dict[str, Any], index: int, region_id: str) -> WeatherRow:
    # Open-Meteo's offset-free strings are UTC only after envelope metadata checks.
    ts = utc_timestamp(hourly["time"][index], assume_utc=True)
    speed = number(hourly["wind_speed_10m"][index], "wind_speed", 0)
    direction = number(hourly["wind_direction_10m"][index], "wind_dir_deg", 0, 360) % 360
    temp = number(hourly["temperature_2m"][index], "temp")
    pressure = number(hourly["surface_pressure"][index], "pressure", 0)
    if pressure == 0:
        raise RowRejected("pressure: must be positive")
    return region_id, ts, speed, direction, temp, pressure
