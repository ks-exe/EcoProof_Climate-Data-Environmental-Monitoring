# Silver build (task 3)

## Run and outputs

```text
uv run --locked make build "ARGS=--region delhi --start-date 2026-10-05 --end-date 2026-10-11"
```

`--region` is required. Dates must be provided together or both omitted. Omitting
them includes all cached timestamps selected for that region. The build performs
no API calls and does not require credentials.

Each successful build writes three Parquet files plus `build_report.json` into
its own `data/silver/build-<id>/` directory. A single transaction updates the three
DuckDB views to these complete files:

| View | Key | Columns |
| --- | --- | --- |
| `silver.stations` | `station_id` | `station_id`, `name`, `lat`, `lon`, `provider`, `cluster_id` |
| `silver.readings` | `(station_id, ts, parameter)` | `station_id`, `ts`, `parameter`, `value`, `unit` |
| `silver.weather` | `(region_id, ts)` | `region_id`, `ts`, `wind_speed`, `wind_dir_deg`, `temp`, `pressure` |

Column types follow spec section 4. Temporary in-memory DuckDB tables enforce
primary keys, the reading-to-station foreign key, null checks, and numerical
constraints before export. The public objects are views over Parquet, not writable
tables; Parquet itself does not enforce primary/check constraints on outside edits.

Earlier build directories are retained. If validation or view publication fails,
the previous published views remain available. A failed file write can leave an
unreferenced build directory; it is not selected by the views. No automatic
deletion of saved builds is performed. Query the views or the exact files listed
in the current report, rather than scanning every previous build. View paths are
absolute; rerun the build after moving the data directory or repository.

## Validation rules

- **Station metadata:** positive OpenAQ location ID, explicitly stationary,
  at least one PM2.5 sensor, finite WGS84 coordinates within latitude ±90 and
  longitude ±180. Optional name/provider text remains null if absent. IDs become
  text and `cluster_id` is the selected region ID.
- **Readings:** require a valid station and a matching PM2.5 sensor in its catalog
  metadata. Parameter ID/name must be `2`/`pm25`; value must be a finite number
  within **0–1500 inclusive**. Booleans, numeric strings, nulls, NaN, and infinities
  are rejected. Equivalent spellings `µg/m³`, `μg/m³`, `ug/m3`, and `µg/m3` normalize
  to `µg/m³`; other units are rejected without guessing a conversion.
- **Weather:** require UTC offset 0 and explicit units of m/s, degrees, Celsius,
  and hPa, with equally sized hourly arrays. Each row needs finite values, wind
  speed ≥0, direction in [0, 360], and pressure >0. Direction 360 normalizes to 0.
  Missing values are rejected and reported, not filled. Negative temperatures and
  calm wind are valid.
- **Source integrity:** reject malformed JSON, unknown Bronze versions/endpoints,
  missing required arrays, mismatched sensor context, unsupported weather units,
  and non-UTC weather metadata. These file-level errors abort publication.

Station/readings/weather row failures are recorded with table, Bronze filename,
zero-based row index, and reason. Valid rows can still be published. A build with
no valid rows of any kind fails instead of replacing the prior build. A weather-only
build is allowed and explicitly reports empty air tables plus a coverage warning.
Provider quality flags and full original metadata remain available in Bronze;
this step does not classify readings or treat provider flags as EcoProof labels.

## UTC and duplicate handling

OpenAQ's `period.datetimeTo.utc` represents the end of its measurement interval.
An explicit timestamp timezone is required. Convert to UTC and keep that instant;
do not subtract an hour or change the reported interval. Open-Meteo's offset-free
strings are interpreted as UTC only after checking `utc_offset_seconds == 0`.

The spec uses `TIMESTAMP`, so stored values are timezone-naive microsecond
timestamps with a fixed **UTC meaning**. Applications must preserve that meaning
and append `Z` when serializing UTC strings. No local-machine timezone is used
to interpret provider timestamps. There is no resampling, averaging, interpolation,
or air/weather join in task 3. Later detector work must explicitly handle the
sampling intervals present in real data.

Build date arguments select `[start_date 00:00Z, day_after_end_date 00:00Z)` based
on these normalized timestamps. Excluded boundary rows count as `outside_window`,
not validation failures.

Process Bronze files by `(fetched_at in UTC, filename)`, then their original row
order. For each table's key, the last valid row wins. A newer invalid row is
reported and does not displace an older valid one. Duplicate counts include both
identical and conflicting repeated keys; values are not averaged. Output rows are
sorted by their keys. Rebuilding the same inputs and window produces the same
table contents, even though the output directory ID changes.

## Region selection and coverage

Weather is selected using its saved `request.context.region_id`. OpenAQ catalogs
match the selected weather's request coordinates at four-decimal precision, and
readings must map back to that catalog. This prevents combining separate cities
when multiple regions are cached. If there is no matching weather, a single
catalog center can be explicitly named by `--region`; multiple centers require
matching weather first. Matching uses request coordinates, not the returned
weather model's grid-cell center.

The build report contains actual row counts, rejection details, duplicate counts,
the UTC window, Bronze input hashes, and each station's reading count, distinct
UTC dates, and first/last timestamp. It warns if fewer than eight stations have
readings on seven UTC dates. Distinct dates do not demonstrate continuous hourly
coverage or sufficient neighbors; those must be assessed on actual OpenAQ data.
No evaluation metrics are produced here.

The verified local dataset currently has 168 real weather rows and no OpenAQ
stations/readings. Its coverage warning is expected. The API key and real station
selection remain prerequisites for the spec's air-data milestone. The
[task 5 classifier](CLASSIFIER.md) can build Gold from these views once air data
is available; hashes and batch metadata remain later provenance work.

## Documentation checked

DuckDB's `/docs/stable/` pages redirected to `/docs/current/` on October 19, 2026.
Implementation and tests use DuckDB **1.5.6** from the lockfile. Checked:

- [Python client](https://duckdb.org/docs/current/clients/python/overview.html)
- [Relational API and Parquet writer](https://duckdb.org/docs/current/clients/python/relational_api.html)
- [Parquet files and views](https://duckdb.org/docs/current/data/parquet/overview.html)
- [Timestamp types](https://duckdb.org/docs/current/sql/data_types/timestamp.html)
- [Constraints](https://duckdb.org/docs/current/sql/constraints.html)
- [Create view](https://duckdb.org/docs/current/sql/statements/create_view.html)
- [Finite-number checks](https://duckdb.org/docs/current/sql/functions/numeric.html)
