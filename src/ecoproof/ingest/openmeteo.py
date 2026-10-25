"""Historical regional weather from Open-Meteo in UTC and SI wind units."""

from datetime import date

from ecoproof.ingest.common import CachedHTTP, IngestionError, Pull, validate_coordinates


ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HOURLY_VARIABLES = (
    "wind_speed_10m", "wind_direction_10m", "temperature_2m", "surface_pressure",
)


def fetch_weather(
    http: CachedHTTP, latitude: float, longitude: float, start: date, end: date,
    *, region_id: str, refresh: bool = False,
) -> Pull:
    validate_coordinates(latitude, longitude)
    if start > end:
        raise ValueError("weather start date must not follow end date")
    if not region_id.strip():
        raise ValueError("region_id must not be blank")
    pull = http.get("openmeteo", ARCHIVE_URL, {
        "latitude": latitude, "longitude": longitude,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "hourly": ",".join(HOURLY_VARIABLES), "timezone": "GMT",
        "wind_speed_unit": "ms", "temperature_unit": "celsius",
    }, context={"region_id": region_id}, refresh=refresh)
    hourly = pull.response.get("hourly")
    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
        raise IngestionError("openmeteo: expected hourly time series")
    size = len(hourly["time"])
    if not size or any(not isinstance(hourly.get(key), list) or len(hourly[key]) != size
                       for key in HOURLY_VARIABLES):
        raise IngestionError("openmeteo: missing or inconsistent hourly arrays")
    if pull.response.get("utc_offset_seconds") != 0:
        raise IngestionError("openmeteo: expected UTC timestamps")
    return pull
