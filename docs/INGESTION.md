# Ingestion (task 2)

## Verified API contract

The following official documentation was checked on October 19, 2026:

| Topic | Reference and implementation decision |
| --- | --- |
| OpenAQ authentication | [API keys](https://docs.openaq.org/using-the-api/api-key): send `X-API-Key` only to `api.openaq.org`. Never save headers in Bronze. |
| Station discovery | [Get locations](https://docs.openaq.org/api/operations/locations_get_v3_locations_get): `GET https://api.openaq.org/v3/locations`, `parameters_id=2`, `mobile=false`, ascending IDs. |
| PM2.5 identity | [Parameters](https://docs.openaq.org/resources/parameters): parameter 2 is `pm25`, mass concentration in µg/m³. |
| Search radius | [Geospatial queries](https://docs.openaq.org/using-the-api/geospatial): `coordinates=latitude,longitude`, radius in meters, maximum 25,000. Coordinates in the query are formatted to four decimal places per the endpoint reference. |
| Original readings | [Get measurements](https://docs.openaq.org/api/operations/sensor_measurements_get_v3_sensors__sensors_id__measurements_get): `GET https://api.openaq.org/v3/sensors/{id}/measurements` with `datetime_from` and `datetime_to` in UTC. Uses original reported values, not the hourly aggregation endpoint. |
| Pagination | [Pagination](https://docs.openaq.org/using-the-api/pagination) and [measurement responses](https://docs.openaq.org/resources/measurements): maximum 1,000 per page. `meta.found` can be an integer, string (including lower bounds such as `">1000"`), or null. Use exact totals when available; otherwise continue until a short or empty page. Abort after 100 pages with an explicit error. |
| Time convention | [Dates and times](https://docs.openaq.org/using-the-api/dates-datetimes): OpenAQ timestamps describe the end of measurement intervals. Preserve both provider UTC and local timestamps in Bronze. |
| Rate limits | [Rate limits](https://docs.openaq.org/using-the-api/rate-limits): current documented free limits are 60 requests/minute and 2,000/hour. The CLI spaces network requests at least 1.05 seconds apart. This is a bounded one-off pull, not a scheduled ingestion job. |
| Regional weather | [Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api): `GET https://archive-api.open-meteo.com/v1/archive`, `hourly=wind_speed_10m,wind_direction_10m,temperature_2m,surface_pressure`, `timezone=GMT`, `wind_speed_unit=ms`, `temperature_unit=celsius`. No key for the noncommercial endpoint. |
| HTTP client/testing | HTTPX [transports](https://www.python-httpx.org/advanced/transports/) and [timeouts](https://www.python-httpx.org/advanced/timeouts/): explicit 30-second network inactivity timeouts; HTTP is mocked using `MockTransport` in tests. |

The OpenAQ pagination guide mentions camelCase date names in prose, but the
measurement endpoint reference specifies snake_case query parameters. The code
uses the endpoint reference's `datetime_from` and `datetime_to`.

Open-Meteo's default Best Match may combine weather models. Its docs say ERA5
products can lag five days; the initial weather pull uses October 5–11 to avoid
that delay. Do not describe regional model wind as measured wind at each station.
Data attribution: [OpenAQ](https://openaq.org/), the original providers and licenses
preserved in location metadata, and [Open-Meteo](https://open-meteo.com/).

## Bronze format and cache behavior

Every successful HTTP JSON object is saved as one envelope:

```text
schema_version: 1
source: openaq | openmeteo
fetched_at: UTC ISO timestamp
request:
  url: documented provider URL
  params: actual query parameters, including page and date bounds
  context: location_id + sensor_id for readings, or region_id for weather
response: original provider JSON object
```

This is raw provider data inside a metadata envelope. JSON is reserialized;
whitespace is not preserved, but field values are not normalized, rounded,
deduplicated, or classified. Nulls, negative readings, provider metadata, licenses,
and time intervals are preserved for task 3. No request headers or keys are saved.

Files use `{source}_{YYYYMMDDTHHMMSSffffffZ}.json`. A complete temporary file is
published through an exclusive hard link, then the temporary name is removed.
An existing Bronze file is never overwritten, including timestamp collisions.
This requires a filesystem supporting hard links; the actual write was verified
on this Windows workspace. Failed publication leaves no final partial JSON.

Matching URL, parameters, and context reuse the most recent cached response.
Changing page, dates, region context, or coordinates makes a different request.
`--refresh` always appends a new snapshot. Cache reuse is explicit by these rules;
it does not claim that cached values are current. Refresh discovery when checking
new station availability. The current OpenAQ client requires its configured key
even for cache replay; the Silver builder reads Bronze directly without a key.

HTTP error responses and invalid JSON are not cached. Structurally unexpected
provider JSON can still be retained as a raw envelope before the provider-specific
check fails; use `--refresh` after fixing or investigating a provider schema change.
Ingestion reports an error, rather than accepting a failed structural check.

## Retry and failure behavior

Transient transport errors and HTTP 408, 429, 500, 502, 503, and 504 are retried
up to three total attempts. Exponential waits start at one and two seconds.
Honor `Retry-After` (seconds or HTTP date), and OpenAQ's `x-ratelimit-reset` when
provided. The OpenAQ page describes reset as a timestamp but illustrates seconds;
the implementation accepts seconds and Unix timestamps. A 429 without usable
headers waits 60 seconds. Longer waits return an explicit retry-later error rather
than retrying early. Permanent failures such as 401/403/422 are not retried, and
redirects are not followed. Error messages exclude response bodies and headers.

Partial runs can leave completed, immutable response pages in Bronze; rerunning
the same request reuses them. No complete-run claim is printed if a later pull
fails. Successful CLI output reports actual response counts and file paths.

## Date and region decisions for task 3

CLI start/end dates are inclusive UTC calendar dates. Open-Meteo receives those
dates directly. OpenAQ receives midnight on the start date through midnight after
the end date, always with `Z`. Bronze retains boundary records as returned. The
Silver builder preserves OpenAQ's interval-ending timestamp, normalizes it to UTC,
and applies a half-open UTC window when build dates are supplied. It does not
resample, interpolate, or shift readings. See [Silver rules](SILVER.md) and the
[classifier's hourly alignment](CLASSIFIER.md) for the downstream handling of
subhourly air measurements and hourly weather.

Station catalog lifetime bounds identify candidates only. The CLI selects up to
`--station-limit` nearby stationary PM2.5 locations, then reports actual records
per station. Fewer than 8–10 usable stations or gaps in the required week must be
flagged before accepting the region. The October 23 live check ingested 7,596
raw readings from 12 Delhi locations across the two cached request windows.
Ten stations cover the output week; two are sparse. See DEMO.md for coverage and
the exact input/calibration dates. Missing hours remain missing.
