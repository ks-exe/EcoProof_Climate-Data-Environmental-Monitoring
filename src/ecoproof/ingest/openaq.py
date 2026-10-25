"""OpenAQ v3 locations and original PM2.5 measurements (not aggregates)."""

from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from ecoproof.ingest.common import CachedHTTP, IngestionError, Pull, validate_coordinates


BASE_URL = "https://api.openaq.org/v3"
PM25_PARAMETER_ID = 2


class OpenAQClient:
    def __init__(self, http: CachedHTTP, api_key: str | None, *, page_size: int = 1000) -> None:
        if not 1 <= page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000")
        self.http = http
        self._api_key = api_key
        self.page_size = page_size

    def locations(
        self, latitude: float, longitude: float, *, radius_m: int = 25000,
        refresh: bool = False,
    ) -> list[Pull]:
        validate_coordinates(latitude, longitude)
        if not 1 <= radius_m <= 25000:
            raise ValueError("radius_m must be between 1 and 25000")
        return list(self._pages("/locations", {
            "coordinates": f"{latitude:.4f},{longitude:.4f}",
            "radius": radius_m, "parameters_id": PM25_PARAMETER_ID,
            "mobile": "false", "order_by": "id", "sort_order": "asc",
        }, refresh=refresh))

    def measurements(
        self, sensor_id: int, location_id: int, start: datetime, end: datetime,
        *, refresh: bool = False,
    ) -> list[Pull]:
        if sensor_id <= 0 or location_id <= 0:
            raise ValueError("sensor_id and location_id must be positive")
        if start.utcoffset() is None or end.utcoffset() is None:
            raise ValueError("measurement bounds must include a timezone")
        if start >= end:
            raise ValueError("measurement start must precede end")
        params = {
            "datetime_from": start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "datetime_to": end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        return list(self._pages(
            f"/sensors/{sensor_id}/measurements", params,
            context={"location_id": location_id, "sensor_id": sensor_id}, refresh=refresh,
        ))

    def _pages(
        self, endpoint: str, params: dict[str, str | int], *,
        context: dict[str, int] | None = None, refresh: bool = False,
    ) -> Iterator[Pull]:
        if not self._api_key:
            raise IngestionError("Set OPENAQ_API_KEY in .env before pulling OpenAQ data")
        seen = 0
        for page in range(1, 101):
            pull = self.http.get(
                "openaq", BASE_URL + endpoint,
                {**params, "limit": self.page_size, "page": page},
                headers={"X-API-Key": self._api_key}, context=context, refresh=refresh,
            )
            results = pull.response.get("results")
            meta = pull.response.get("meta")
            if not isinstance(results, list) or not isinstance(meta, dict):
                raise IngestionError("openaq: expected results list and pagination metadata")
            if meta.get("page") != page:
                raise IngestionError("openaq: response page does not match requested page")
            limit = meta.get("limit", self.page_size)
            if not isinstance(limit, int) or not 1 <= limit <= 1000:
                raise IngestionError("openaq: invalid pagination limit")
            yield pull
            seen += len(results)
            found = meta.get("found")
            if isinstance(found, str) and found.isdecimal():
                found = int(found)
            if isinstance(found, int) and seen >= found:
                return
            if not results:
                if isinstance(found, int) and seen < found:
                    raise IngestionError("openaq: empty page before advertised result count")
                return
            if len(results) < limit and not (isinstance(found, int) and seen < found):
                return
        raise IngestionError("openaq: exceeded 100 pages; request a smaller date window")


def pm25_sensors(location: dict[str, Any]) -> list[int]:
    """Select sensor IDs from provider metadata without changing any readings."""
    return [sensor["id"] for sensor in location.get("sensors", [])
            if sensor.get("parameter", {}).get("id") == PM25_PARAMETER_ID]
