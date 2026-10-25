"""All HTTP in these tests is mocked; fixtures are synthetic, not API results."""

from collections.abc import Callable, Iterator
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from ecoproof.config import Settings
from ecoproof.ingest import __main__ as cli
from ecoproof.ingest.common import CachedHTTP, IngestionError
from ecoproof.ingest.openaq import OpenAQClient
from ecoproof.ingest.openmeteo import ARCHIVE_URL, HOURLY_VARIABLES, fetch_weather


NOW = datetime(2026, 10, 19, 10, tzinfo=timezone.utc)
Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def http_factory(tmp_path: Path) -> Iterator[Callable[..., CachedHTTP]]:
    clients = []

    def create(handler: Handler, **kwargs: Any) -> CachedHTTP:
        client = httpx.Client(transport=httpx.MockTransport(handler))
        clients.append(client)
        return CachedHTTP(client, tmp_path / "bronze", now=lambda: NOW, **kwargs)

    yield create
    for client in clients:
        client.close()


def test_cache_reuses_response_without_saving_credentials(http_factory: Callable[..., CachedHTTP]) -> None:
    requests = []
    payload = {"value": None, "original": [12.125, -5, "station"]}

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["X-API-Key"] == "dummy-secret"
        return httpx.Response(200, json=payload)

    http = http_factory(handler)
    first = http.get("openaq", "https://api.openaq.org/v3/locations", {"page": 1}, headers={"X-API-Key": "dummy-secret"})
    second = http.get("openaq", "https://api.openaq.org/v3/locations", {"page": 1})
    assert len(requests) == 1
    assert not first.from_cache and second.from_cache
    assert first.path == second.path
    saved = json.loads(first.path.read_text(encoding="utf-8"))
    assert saved["response"] == payload
    assert saved["fetched_at"] == "2026-10-19T10:00:00Z"
    assert "dummy-secret" not in first.path.read_text(encoding="utf-8")
    assert "headers" not in saved["request"]


def test_refresh_preserves_old_file_even_when_clock_collides(http_factory: Callable[..., CachedHTTP]) -> None:
    bodies = iter([{"value": 1}, {"value": 2}])
    http = http_factory(lambda request: httpx.Response(200, json=next(bodies)))
    first = http.get("openaq", "https://api.openaq.org/v3/locations", {})
    original = first.path.read_bytes()
    second = http.get("openaq", "https://api.openaq.org/v3/locations", {}, refresh=True)
    assert first.path != second.path
    assert first.path.read_bytes() == original
    assert http.get("openaq", "https://api.openaq.org/v3/locations", {}).response == {"value": 2}
    assert not list(http.bronze_dir.glob(".pending-*"))


def test_request_parameters_and_context_separate_cache_entries(http_factory: Callable[..., CachedHTTP]) -> None:
    http = http_factory(lambda request: httpx.Response(200, json={"ok": True}))
    pulls = [http.get("openaq", "https://api.openaq.org/v3/locations", {"page": page}, context={"region": region})
             for page, region in [(1, "a"), (2, "a"), (1, "b")]]
    assert len({pull.path for pull in pulls}) == 3
    assert all(not pull.from_cache for pull in pulls)


def test_failed_atomic_publish_leaves_no_json_or_temporary_file(
    http_factory: Callable[..., CachedHTTP], monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = http_factory(lambda request: httpx.Response(200, json={"ok": True}))

    def fail_link(*args: Any) -> None:
        raise OSError("simulated disk failure")

    monkeypatch.setattr("ecoproof.ingest.common.os.link", fail_link)
    with pytest.raises(OSError, match="simulated disk failure"):
        http.get("openaq", "https://api.openaq.org/v3/locations", {})
    assert list(http.bronze_dir.iterdir()) == []


@pytest.mark.parametrize("status", [408, 500, 502, 503, 504])
def test_transient_http_error_retries(status: int, http_factory: Callable[..., CachedHTTP]) -> None:
    responses = iter([httpx.Response(status), httpx.Response(200, json={"ok": True})])
    delays = []
    http = http_factory(lambda request: next(responses), sleep=delays.append)
    assert http.get("openaq", "https://api.openaq.org/v3/locations", {}).response == {"ok": True}
    assert delays == [1.0]


@pytest.mark.parametrize("headers,expected", [
    ({"Retry-After": "12"}, 12.0),
    ({"Retry-After": "Mon, 19 Oct 2026 10:00:10 GMT"}, 10.0),
    ({"x-ratelimit-reset": "15"}, 15.0),
    ({"x-ratelimit-reset": str(int(NOW.timestamp()) + 20)}, 20.0),
    ({"Retry-After": "not-a-date"}, 60.0),
    ({}, 60.0),
])
def test_rate_limit_respects_server_wait(
    headers: dict[str, str], expected: float, http_factory: Callable[..., CachedHTTP],
) -> None:
    responses = iter([httpx.Response(429, headers=headers), httpx.Response(200, json={"ok": True})])
    delays = []
    http = http_factory(lambda request: next(responses), sleep=delays.append)
    http.get("openaq", "https://api.openaq.org/v3/locations", {})
    assert delays == [expected]


def test_long_rate_limit_fails_without_retrying_early(http_factory: Callable[..., CachedHTTP]) -> None:
    delays = []
    http = http_factory(lambda request: httpx.Response(429, headers={"Retry-After": "3600"}), sleep=delays.append)
    with pytest.raises(IngestionError, match="retry after 3600 seconds"):
        http.get("openaq", "https://api.openaq.org/v3/locations", {})
    assert delays == []
    assert not list(http.bronze_dir.glob("*.json"))


def test_network_timeout_then_success(http_factory: Callable[..., CachedHTTP]) -> None:
    requests = []
    delays = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ReadTimeout("simulated timeout")
        return httpx.Response(200, json={"ok": True})

    http = http_factory(handler, sleep=delays.append)
    http.get("openaq", "https://api.openaq.org/v3/locations", {})
    assert len(requests) == 2 and delays == [1.0]


def test_retry_exhaustion_uses_exponential_backoff(http_factory: Callable[..., CachedHTTP]) -> None:
    delays = []
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503)

    http = http_factory(handler, sleep=delays.append)
    with pytest.raises(IngestionError, match="exhausted 3 attempts"):
        http.get("openaq", "https://api.openaq.org/v3/locations", {})
    assert len(requests) == 3 and delays == [1.0, 2.0]
    assert not list(http.bronze_dir.glob("*.json"))


@pytest.mark.parametrize("status", [302, 400, 401, 403, 404, 422])
def test_permanent_errors_and_redirects_are_not_retried(
    status: int, http_factory: Callable[..., CachedHTTP],
) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, text="dummy-secret", headers={"Location": "https://other.invalid"})

    http = http_factory(handler)
    with pytest.raises(IngestionError) as error:
        http.get("openaq", "https://api.openaq.org/v3/locations", {})
    assert str(status) in str(error.value)
    assert "dummy-secret" not in str(error.value)
    assert len(requests) == 1
    assert not list(http.bronze_dir.glob("*.json"))


@pytest.mark.parametrize("body", [b"broken-json", b"[]", b'{"error":true}'])
def test_invalid_or_error_json_is_not_cached(body: bytes, http_factory: Callable[..., CachedHTTP]) -> None:
    http = http_factory(lambda request: httpx.Response(200, content=body))
    with pytest.raises(IngestionError):
        http.get("openmeteo", ARCHIVE_URL, {})
    assert not list(http.bronze_dir.glob("*.json"))


@pytest.mark.parametrize("found", [4, "4", ">2", None])
def test_openaq_pagination_including_non_numeric_totals(
    found: int | str | None, http_factory: Callable[..., CachedHTTP],
) -> None:
    pages = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3/locations"
        assert request.url.params["parameters_id"] == "2"
        assert request.url.params["coordinates"] == "28.6139,77.2090"
        assert request.url.params["radius"] == "25000"
        assert request.url.params["mobile"] == "false"
        assert request.headers["X-API-Key"] == "dummy-key"
        page = int(request.url.params["page"])
        pages.append(page)
        rows = [{"id": page * 2 - 1}, {"id": page * 2}] if page <= 2 else []
        return httpx.Response(200, json={"meta": {"page": page, "limit": 2, "found": found}, "results": rows})

    pulls = OpenAQClient(http_factory(handler), "dummy-key", page_size=2).locations(28.6139, 77.209)
    assert sum(len(pull.response["results"]) for pull in pulls) == 4
    assert pages == ([1, 2] if found in (4, "4") else [1, 2, 3])


def test_openaq_short_page_stops_unknown_total(http_factory: Callable[..., CachedHTTP]) -> None:
    http = http_factory(lambda request: httpx.Response(200, json={
        "meta": {"page": 1, "limit": 1000, "found": None}, "results": [{"id": 1}],
    }))
    assert len(OpenAQClient(http, "dummy-key").locations(0, 0)) == 1


def test_openaq_measurement_bounds_and_mapping_are_saved(http_factory: Callable[..., CachedHTTP]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3/sensors/123/measurements"
        assert request.url.params["datetime_from"] == "2026-10-18T19:00:00Z"
        assert request.url.params["datetime_to"] == "2026-10-19T19:00:00Z"
        assert "datetimeFrom" not in request.url.params
        return httpx.Response(200, json={"meta": {"page": 1, "limit": 1000, "found": 1}, "results": [{"value": -1}]})

    start = datetime(2026, 10, 19, tzinfo=timezone(timedelta(hours=5)))
    pulls = OpenAQClient(http_factory(handler), "dummy-key").measurements(123, 456, start, start + timedelta(days=1))
    saved = json.loads(pulls[0].path.read_text(encoding="utf-8"))
    assert saved["request"]["context"] == {"sensor_id": 123, "location_id": 456}
    assert saved["response"]["results"][0]["value"] == -1  # validation belongs to Silver


def test_openaq_rejects_missing_key_before_network(http_factory: Callable[..., CachedHTTP]) -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("network must not be called")

    with pytest.raises(IngestionError, match="OPENAQ_API_KEY"):
        OpenAQClient(http_factory(forbidden), None).locations(0, 0)


def test_openaq_rejects_page_mismatch(http_factory: Callable[..., CachedHTTP]) -> None:
    http = http_factory(lambda request: httpx.Response(200, json={"meta": {"page": 1}, "results": [{"id": 1}]}))
    with pytest.raises(IngestionError, match="does not match"):
        list(OpenAQClient(http, "dummy-key", page_size=1).locations(0, 0))


def weather_payload() -> dict[str, Any]:
    return {
        "utc_offset_seconds": 0,
        "hourly": {"time": ["2026-10-10T00:00", "2026-10-10T01:00"],
                   "wind_speed_10m": [0.0, None], "wind_direction_10m": [180, None],
                   "temperature_2m": [25.0, 24.0], "surface_pressure": [1000, 1001]},
    }


def test_weather_request_uses_utc_ms_and_preserves_nulls(http_factory: Callable[..., CachedHTTP]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(ARCHIVE_URL)
        assert request.url.params["timezone"] == "GMT"
        assert request.url.params["wind_speed_unit"] == "ms"
        assert request.url.params["temperature_unit"] == "celsius"
        assert request.url.params["start_date"] == "2026-10-10"
        assert request.url.params["end_date"] == "2026-10-10"
        assert request.url.params["hourly"].split(",") == list(HOURLY_VARIABLES)
        assert "X-API-Key" not in request.headers
        return httpx.Response(200, json=weather_payload())

    pull = fetch_weather(http_factory(handler), 28.6139, 77.209, date(2026, 10, 10), date(2026, 10, 10), region_id="test")
    assert pull.response == weather_payload()
    assert json.loads(pull.path.read_text(encoding="utf-8"))["request"]["context"] == {"region_id": "test"}


@pytest.mark.parametrize("change", ["offset", "array", "empty"])
def test_weather_rejects_unusable_structure(change: str, http_factory: Callable[..., CachedHTTP]) -> None:
    payload = weather_payload()
    if change == "offset":
        payload["utc_offset_seconds"] = 18000
    elif change == "array":
        payload["hourly"]["wind_speed_10m"] = [1]
    else:
        payload["hourly"]["time"] = []
    http = http_factory(lambda request: httpx.Response(200, json=payload))
    with pytest.raises(IngestionError):
        fetch_weather(http, 0, 0, date(2026, 10, 10), date(2026, 10, 10), region_id="test")


@pytest.mark.parametrize("latitude,longitude", [(91, 0), (0, 181), (float("nan"), 0)])
def test_coordinates_are_validated_before_network(
    latitude: float, longitude: float, http_factory: Callable[..., CachedHTTP],
) -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("network must not be called")

    http = http_factory(forbidden)
    with pytest.raises(ValueError):
        OpenAQClient(http, "dummy-key").locations(latitude, longitude)
    with pytest.raises(ValueError):
        fetch_weather(http, latitude, longitude, date(2026, 10, 10), date(2026, 10, 10), region_id="test")


def test_cli_pulls_both_sources_and_reports_cache_reuse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "archive-api.open-meteo.com":
            assert "X-API-Key" not in request.headers
            return httpx.Response(200, json=weather_payload())
        assert request.headers["X-API-Key"] == "dummy-key"
        if request.url.path == "/v3/locations":
            results = [{"id": 1, "name": "Synthetic test station", "isMobile": False,
                        "sensors": [{"id": 2, "parameter": {"id": 2}}]}]
        else:
            assert request.url.path == "/v3/sensors/2/measurements"
            results = [{"value": 12.0}]
        return httpx.Response(200, json={"meta": {"page": 1, "limit": 1000, "found": 1}, "results": results})

    real_client = httpx.Client
    monkeypatch.setattr(cli.httpx, "Client", lambda: real_client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(cli, "load_settings", lambda: Settings(tmp_path / "data", openaq_api_key="dummy-key"))
    monkeypatch.setattr(cli, "CachedHTTP", lambda client, directory, **kwargs: CachedHTTP(client, directory))
    args = cli.parser().parse_args(["--region", "test", "--latitude", "0", "--longitude", "0",
                                  "--start-date", "2026-10-10", "--end-date", "2026-10-10"])
    first = cli.run(args)
    second = cli.run(args)
    assert first["new_bronze_files"] == 3 and first["cached_responses"] == 0
    assert first["stations_with_readings"] == 1 and first["raw_readings"] == 1
    assert first["weather_hours"] == 2 and first["weather_non_null_wind_hours"] == 1
    assert second["new_bronze_files"] == 0 and second["cached_responses"] == 3
    assert len(requests) == 3


def test_cli_catalog_filter_excludes_mobile_wrong_parameter_and_stale_stations() -> None:
    station = {"id": 1, "isMobile": False, "sensors": [{"id": 2, "parameter": {"id": 2}}]}
    candidates = [station, {**station, "id": 2, "isMobile": True},
                  {**station, "id": 3, "sensors": []},
                  {**station, "id": 4, "datetimeLast": {"utc": "2020-01-01T00:00:00Z"}}]
    assert cli.eligible_locations(candidates, NOW - timedelta(days=7), NOW) == [station]
