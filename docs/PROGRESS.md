# EcoProof progress

## Task 1 — repository scaffold

Date: October 19, 2026. Status: **complete; user authorized task 2**.
The entry below records the task 1 handoff.

### What was built

- Initialized a local Git repository on `main`. No commit, remote, or push was made.
- The workspace was initially empty: neither `AGENTS.md` nor `docs/SPEC.md` existed,
  and no parent `AGENTS.md` was found. Read all seven pages of the supplied
  `C:\Users\arfar\Downloads\EcoProof_Implementation_Spec.pdf`, transcribed the full
  spec to Markdown, and created `AGENTS.md` from its section 10 plus the user's
  session rules. Read both resulting files fully before implementing the scaffold.
  The spec has not been rewritten after its initial creation.
- Created the section 3 package paths and directory placeholders. Later features
  are explicitly pending. No API endpoints, detector, smart contract, frontend,
  ingestion logic, data, evaluation metrics, or blockchain results were fabricated.
- Implemented typed configuration loading from root `.env` plus environment
  overrides, literal credential values, hidden credentials in settings output,
  and data paths resolved relative to the repository root.
- Added Python packaging, `.python-version`, a generated `uv.lock`, pytest, and
  GNU Make for Windows. Set up `.venv` with Python 3.11.15.
- Added all Make targets listed in the spec. `test` runs pytest; the later task
  targets fail with explicit pending-task errors.
- Added setup, architecture, command, and limitations documentation. Created an
  ignored local `.env` from `.env.example`, with blank credentials.

### Files changed

All files below are new:

| Area | Files |
| --- | --- |
| Project instructions and documentation | `AGENTS.md`, `README.md`, `docs/SPEC.md`, `docs/PROGRESS.md` |
| Setup and tooling | `.env.example`, `.gitignore`, `.gitattributes`, `.python-version`, `pyproject.toml`, `uv.lock`, `Makefile` |
| Configuration | `src/ecoproof/__init__.py`, `src/ecoproof/config.py` |
| Ingestion placeholders | `src/ecoproof/ingest/__init__.py`, `src/ecoproof/ingest/openaq.py`, `src/ecoproof/ingest/openmeteo.py` |
| Transform placeholders | `src/ecoproof/transform/__init__.py`, `src/ecoproof/transform/silver.py`, `src/ecoproof/transform/gold.py` |
| Graph placeholders | `src/ecoproof/graph/__init__.py`, `src/ecoproof/graph/geo.py` |
| Detection placeholders | `src/ecoproof/detect/__init__.py`, `src/ecoproof/detect/classifier.py`, `src/ecoproof/detect/inject.py`, `src/ecoproof/detect/evaluate.py` |
| Provenance placeholders | `src/ecoproof/provenance/__init__.py`, `src/ecoproof/provenance/merkle.py`, `src/ecoproof/provenance/anchor.py` |
| API and stretch placeholders | `src/ecoproof/api/__init__.py`, `src/ecoproof/api/main.py`, `src/ecoproof/sqlchat/__init__.py`, `src/ecoproof/sqlchat/guard.py` |
| Local data/report layout | `data/README.md`, `data/bronze/.gitkeep`, `data/silver/.gitkeep`, `data/gold/.gitkeep`, `reports/.gitkeep` |
| Contract layout | `contracts/README.md`, `contracts/BatchRegistry.sol`, `contracts/test/.gitkeep`, `contracts/script/deploy` |
| Frontend layout | `web/README.md` |
| Tests | `tests/test_config.py` |

Local generated files also include `.env`, `.venv/`, and `.pytest_cache/`; these
are ignored. `data/ecoproof.duckdb` is a configured runtime path, not an empty fake
database file; storage implementation in task 3 will create it.

### Tests run and actual results

Platform: Windows, Python 3.11.15, pytest 9.1.1, GNU Make 4.4.1.

The final required checks completed successfully, exit code 0:

```text
> uv run --locked make test
python -m pytest -q
.......                                                                  [100%]
7 passed in 0.30s

> uv run --locked pytest -q
.......                                                                  [100%]
7 passed in 0.23s
```

The seven offline tests cover defaults without credentials or data creation,
`.env` loading without changing `os.environ`, environment precedence, blank
credential overrides, relative paths independent of working directory, absolute
data paths, and literal/redacted credentials. Test credentials are obvious dummy
strings; `.invalid` URLs are test inputs and are never called.

Earlier failed attempts are recorded for completeness:

- The sandbox initially blocked uv's cache (`Access is denied`); no tests ran in
  that attempt. Retried with approved execution outside the sandbox.
- The first actual `make test` reached pytest but reported `7 errors in 5.05s`.
  All errors were fixture setup failures due to access being denied to the shared
  `C:\Users\arfar\AppData\Local\Temp\pytest-of-arfar` directory. Added
  `--basetemp=.pytest_cache/tmp` to pytest configuration, verified that this path
  resolves inside the repository, and reran both checks successfully as shown above.

Additional checks run:

- `uv run --locked python --version`: `Python 3.11.15`.
- `uv run --locked make --version`: `GNU Make 4.4.1`, built for Windows32.
- `uv run --locked make help`: displayed the scaffold commands successfully.
- Invoked `make ingest`, `build`, `detect`, `eval`, `anchor`, `api`, and `web`
  through `uv run --locked`. Each returned nonzero with its expected pending-task
  message. Example actual output:

  ```text
  Makefile:15: *** Task 2 pending: OpenAQ and Open-Meteo ingestion is not implemented.  Stop.
  ```

- `git check-ignore` confirmed that `.env`, `.env.local`, `web/.env`, raw JSON,
  Parquet data, DuckDB files, and `.venv` are ignored; `.env.example` and all three
  data `.gitkeep` files are not ignored. `git status` showed only scaffold source
  and documentation files as untracked.
- Compared word/number tokens from all PDF pages against the Markdown spec.
  The eight differences were limited to PDF running page headers, repeated table
  headings, and the title's placement. This checks textual content, not PDF visual
  layout or mathematical punctuation.

### Uncertainties and decisions

- Resolved the absent source files using the supplied PDF rather than guessing
  project requirements. No substantive spec change was proposed or made.
- The spec says Python 3.11+ while its AGENTS block asks for Python 3.11. Used
  Python 3.11 for development/testing and retained `>=3.11` in package metadata.
- GNU Make was absent. Checked PyPI metadata before choosing the `gnumake` 4.4.1
  Windows wheel; the package named `make` is unrelated. References:
  <https://pypi.org/pypi/gnumake/json>, <https://github.com/xmake-io/gnumake-wheel>.
- Only task 1 dependencies are installed. FastAPI, DuckDB, web3.py, React/Vite/
  Leaflet, and a contract toolchain will be introduced with their implementation
  tasks. Foundry versus Hardhat and the target testnet remain undecided.
- No API detail was assumed or endpoint called. Task 2 must verify current
  OpenAQ v3 and Open-Meteo documentation and select a sufficiently dense region
  before claiming a successful real pull.
- No task 1 blocker remains. Tests have been run on Windows only.

### Next task

**Task 2, after user review:** implement `ingest/openaq.py` and
`ingest/openmeteo.py` with immutable Bronze caching and retry/backoff. Mock HTTP
in tests, run them, and save one real API pull. Update this file with actual
results, then stop again for review.

## Task 2 — OpenAQ and Open-Meteo ingestion

Date: October 19, 2026. Status: **implemented; acceptance checks met; user authorized task 3**.
Tests passed and one real Open-Meteo pull was saved. **Live OpenAQ validation is
pending a configured API key.** The entry below records the task 2 handoff.

### What was built

- OpenAQ v3 station discovery for stationary PM2.5 locations within a validated
  radius, and original measurements by sensor ID with explicit UTC date bounds.
  Pagination handles exact numeric totals, numeric strings, lower-bound strings,
  and missing totals; it verifies page numbers and has a 100-page safety limit.
- Open-Meteo historical regional weather for wind speed, direction, temperature,
  and surface pressure. Requests use UTC, m/s, Celsius, and hPa.
- Shared HTTP fetching with 30-second inactivity timeouts, three-attempt bounded
  retry/backoff, server retry timing, permanent-error handling, and no redirects.
  The CLI spaces live requests at least 1.05 seconds apart.
- Immutable Bronze envelopes containing request metadata and provider JSON. No
  headers or credentials are saved. Matching requests reuse existing files;
  `--refresh` appends new snapshots. Atomic publication avoids partial JSON and
  never overwrites existing files, including timestamp collisions.
- `python -m ecoproof.ingest` / `make ingest ARGS="..."` for catalog-only,
  OpenAQ-only, weather-only, and combined pulls, with actual counts in CLI output.
- Locked HTTPX 0.28.1, mocked HTTP tests, updated setup and commands, and API/cache
  contract documentation. Bronze values remain uncleaned for task 3.

### Files changed in task 2

- Implemented `src/ecoproof/ingest/openaq.py` and `openmeteo.py`.
- Added `src/ecoproof/ingest/common.py` and `__main__.py`; updated the package's
  `__init__.py` description.
- Added `tests/test_ingest.py` (44 cases, including parameterized cases).
- Updated `pyproject.toml`, `uv.lock`, `Makefile`, `.env.example`, `README.md`,
  `data/README.md`, and this progress file.
- Added `docs/INGESTION.md` with the checked official references, request details,
  cache format, retry behavior, and timestamp caveats for task 3.
- Created the ignored local real-data file
  `data/bronze/openmeteo_20261019T125448550421Z.json` (8,237 bytes).
- `docs/SPEC.md` was read in full and was not modified. Its SHA-256 before and
  after task 2 is
  `8307cf224dc66ca6767b0842817fbe4f37ef4d830ab2572c778edb79880f2395`.
- No secrets, `.env` edits, commits, or pushes were made in task 2. All source
  files remain uncommitted, as they were at the start of this task.

### Tests run and actual results

Windows, Python 3.11.15, HTTPX 0.28.1, pytest 9.1.1. Both commands exited 0:

```text
> uv run --locked make test
python -m pytest -q
...................................................                      [100%]
51 passed in 2.40s

> uv run --locked pytest -q
...................................................                      [100%]
51 passed in 1.74s
```

The suite comprises the existing seven configuration tests plus 44 ingestion
cases. HTTP is entirely mocked in tests. Checks include transient/permanent HTTP
failures, transport timeout recovery, retry exhaustion and timing, redirects,
invalid JSON, authentication omission, cache reuse/isolation, immutable refresh
and collision handling, publication failure, pagination, UTC measurement bounds,
sensor-to-location context, weather units/nulls/shape, coordinate validation, and
both CLI sources together. Synthetic test values are not project data or metrics.

The following real command also exited 0:

```text
uv run --locked make ingest "ARGS=--source openmeteo --region delhi --latitude 28.6139 --longitude 77.2090 --start-date 2026-10-05 --end-date 2026-10-11"
```

Actual output fields from the first pull:

```json
{
  "region_id": "delhi",
  "source": "openmeteo",
  "weather_hours": 168,
  "weather_non_null_wind_hours": 168,
  "new_bronze_files": 1,
  "cached_responses": 0
}
```

The CLI additionally printed the saved file's absolute path. Inspection of that
file confirmed UTC offset 0, timestamps `2026-10-05T00:00` through
`2026-10-11T23:00`, wind in m/s/degrees, temperature in Celsius, and surface
pressure in hPa. These are raw weather response counts, not detection metrics.

Repeated the identical command and observed:

```json
{
  "weather_hours": 168,
  "weather_non_null_wind_hours": 168,
  "new_bronze_files": 0,
  "cached_responses": 1
}
```

The saved file's SHA-256 before and after replay was unchanged:
`89e91f8509e7c9a720e0430b592a57410d1c5733be363274edf79df9457283c3`.
`make help` succeeded. `git check-ignore` confirmed that `.env` and this real
Bronze file are ignored; Git status contains source/documentation only.

The attempted OpenAQ catalog command exited 1 before sending an API request:

```text
Set OPENAQ_API_KEY in .env before pulling OpenAQ data
```

The config loader was checked again after the weather replay:

```text
OpenAQ key configured: False
```

An earlier ad-hoc raw-text check had incorrectly indicated a key was present;
that was corrected using the project's actual config loader. No key value was
printed. The user was asked to add the key to `.env` rather than share it in chat.

### Uncertainties, limitations, and deadline risk

- OpenAQ paths, parameters, response shapes, and authentication were checked
  against official documentation, but the live service has not been validated
  because the key is absent. Mock tests cannot establish live station availability.
- Delhi is a candidate coordinate for the verified weather pull, not an accepted
  air-quality region. No count of real OpenAQ stations or air readings is claimed.
  The spec's 8–10 stations and seven-day coverage requirement remains unverified.
  Resolving this promptly matters to the six-day schedule.
- OpenAQ's pagination prose and endpoint reference differ on date-parameter
  naming; implemented the endpoint reference's snake_case parameters. Its reset
  header description and example also differ; support both seconds and epoch time.
- Original JSON values are preserved inside metadata envelopes, but original
  whitespace is not. Structurally unexpected HTTP-200 JSON may remain in Bronze
  before provider-specific checks fail; the command does not report it as success.
- The OpenAQ client currently requires a key even for its cache replay. Task 3
  will read saved Bronze envelopes directly without API access.
- Hard-link publication was verified on the actual Windows workspace. Other
  filesystems/platforms were not tested. There is no recurring ingestion job.
- Weather is regional reanalysis/model output. Task 3 must handle missing values,
  align UTC times with OpenAQ's interval-ending timestamps, and validate actual
  coverage. No Silver transformations or database work were performed here.

### Next task

**Task 3, after user review:** build Silver validation, deduplication, UTC
normalization, Parquet files, and DuckDB views, with tests rejecting constraint
violations. Obtain and inspect real OpenAQ Bronze data with the existing task 2
client once the key is configured; confirm a suitable region and week before
claiming the data-coverage milestone. Update this file and stop for review.

## Task 3 — Silver validation, Parquet, and DuckDB views

Date: October 19, 2026. Status: **implemented and tested; user authorized task 4**.
The entry below records the task 3 handoff. The real build was weather-only
because the OpenAQ key was absent; the air-data coverage milestone remained unmet.

### What was built

- An offline Bronze-to-Silver builder for stations, readings, and weather using
  the columns and types from spec section 4.
- Row validation for PM2.5 bounds (0–1500 inclusive), finite numbers, pollutant and
  mass units, stationary station metadata, WGS84 coordinate ranges, sensor/station
  references, UTC timestamps, and weather values/units.
- Deterministic deduplication by each table's key. The latest valid pull wins,
  ordered by fetch timestamp, filename, and original row order. Invalid rows are
  excluded and recorded with their source file, row index, and reason.
- UTC normalization preserving OpenAQ's interval-ending instant. Optional paired
  date arguments select a half-open UTC window. No interpolation or resampling.
- DuckDB staging tables with primary, foreign, null, and check constraints,
  followed by sorted, compressed Parquet output. Public `silver.stations`,
  `silver.readings`, and `silver.weather` views reference the completed files.
- A single transaction switches all three views to each new build. Earlier files
  remain intact. Malformed source input or failed publication preserves the
  previously published views. Each build has a JSON report and input hashes.
- `make build ARGS="--region ..."`, actual coverage reporting, and documentation
  of validation, timestamp interpretation, partial datasets, and storage behavior.
- DuckDB 1.5.6 added to the lockfile. Official DuckDB docs were checked through
  their verified `/docs/current/` redirect targets; references are in `docs/SILVER.md`.

### Files changed in task 3

- Implemented `src/ecoproof/transform/silver.py`.
- Added `src/ecoproof/transform/validation.py` and `__main__.py`; updated
  `src/ecoproof/transform/__init__.py`.
- Added `tests/test_silver.py` with 54 cases, including parameterized cases.
- Updated `pyproject.toml`, `uv.lock`, `Makefile`, `README.md`, `data/README.md`,
  `docs/INGESTION.md`, and this progress file.
- Added `docs/SILVER.md`.
- Created the ignored real `data/ecoproof.duckdb` database and Silver outputs.
  The active build is `data/silver/build-658f770385ba4ac5ab0334303056fc18/`, containing
  `stations.parquet`, `readings.parquet`, `weather.parquet`, and `build_report.json`.
  The first build directory is retained as an earlier snapshot.
- `.env` and `.env.example` needed no changes: no new configuration variables or
  credentials were introduced. No commits or pushes were made.
- `docs/SPEC.md` was read fully and not changed. Its SHA-256 remains
  `8307cf224dc66ca6767b0842817fbe4f37ef4d830ab2572c778edb79880f2395`.

### Tests run and actual results

Windows, Python 3.11.15, DuckDB 1.5.6, pytest 9.1.1. The final required checks both
exited 0:

```text
> uv run --locked make test
python -m pytest -q
........................................................................ [ 68%]
.................................                                        [100%]
105 passed in 9.87s

> uv run --locked pytest -q
........................................................................ [ 68%]
.................................                                        [100%]
105 passed in 9.42s
```

The 105 cases include the previous 51 tests plus 54 Silver cases. New checks cover
invalid/out-of-range/nonfinite values, units and pollutants, timezone requirements,
coordinate validation, mobile stations, orphan readings, latest-valid deduplication,
weather nulls, date boundaries, multiple-region isolation, typed Parquet round trips,
real DuckDB primary/foreign/check constraint rejection, deterministic rebuilds,
Bronze immutability, and rollback when one new view's Parquet file is missing.
All air-quality test fixtures are explicitly synthetic and stay in pytest's scratch
directory; no synthetic records were copied into project data.

The first test run also passed (`105 passed in 12.97s` via Make and
`105 passed in 11.23s` directly). The suite was rerun after correcting the Windows
build-directory permission issue described below.

Real-data command, exit 0:

```text
uv run --locked make build "ARGS=--region delhi --start-date 2026-10-05 --end-date 2026-10-11"
```

Actual output fields:

```json
{
  "region_id": "delhi",
  "counts": {
    "stations": 0,
    "readings": 0,
    "weather": 168
  },
  "rejected_rows": 0,
  "window_start_utc": "2026-10-05T00:00:00Z",
  "window_end_exclusive_utc": "2026-10-12T00:00:00Z",
  "station_coverage": [],
  "warnings": [
    "Fewer than 8 stations have valid readings on 7 UTC dates; the air-data milestone is not met."
  ]
}
```

A separate read-only query from the normal workspace returned:

```text
Counts: [('stations', 0), ('readings', 0), ('weather', 168)]
Weather UTC range: (datetime.datetime(2026, 10, 5, 0, 0), datetime.datetime(2026, 10, 11, 23, 0), 7)
Timestamp type: ('TIMESTAMP',)
OpenAQ key configured: False
```

Also ran `make help`, inspected the saved build report, and checked Git ignore
rules for `.env`, DuckDB, Parquet, and reports. All local data outputs are ignored.
The real Bronze weather file's SHA-256 stayed unchanged after both builds:
`89e91f8509e7c9a720e0430b592a57410d1c5733be363274edf79df9457283c3`.

### Issues resolved, uncertainties, and limitations

- The first real build succeeded, but a sandboxed read-only query reported that
  its Parquet files could not be found. Approved execution outside the sandbox
  successfully queried those same files, identifying a directory permission issue.
  Python's temporary-directory creation had given persistent output directories
  restrictive permissions. Changed build output creation to normal workspace
  directories, rebuilt, and verified the normal sandboxed query succeeds. The
  final counts above are from that normal workspace query.
- OpenAQ is still unconfigured. There are no real station/air-reading rows to
  validate. Current tests establish transformation behavior on synthetic fixtures,
  not real OpenAQ coverage. This remains a deadline risk for the 8–10-station,
  seven-day milestone; the existing ingestion client can be used once the key is set.
- Weather rows with any missing required field are rejected; no values are
  invented. Weather is regional model/reanalysis output, not station-level wind
  observations. Unit and pressure checks are documented implementation decisions.
- The spec's `TIMESTAMP` type is retained with a fixed UTC meaning. Consumer APIs
  must serialize it as UTC. Sampling intervals and an air/weather join remain
  explicit work for the detector stage, rather than silently averaging raw data.
- Public objects are Parquet-backed views. Constraints are enforced in the build;
  direct external edits to Parquet bypass that build validation.
- Older build folders are retained and current views contain absolute paths.
  Rebuild after moving the repository/data directory. Gold tables and classifier
  output remain unimplemented; no work beyond task 3 was done.

### Next task

**Task 4, after user review:** implement `graph/geo.py` with haversine distances,
adjacency using tau and sigma, and wind weighting with the correct meteorological
direction convention. Run known-distance and wind-direction unit tests, update
this file, and stop for review. Real station coverage still needs the OpenAQ key
and a real ingestion/build run before claiming the air-data milestone.

## Task 4 — geographic graph and wind weights

Date: October 20, 2026. Status: **implemented and tested; user authorized task 5**.
The entry below records the task 4 handoff.

### What was built

- Typed, standard-library graph functions in `graph/geo.py`: `haversine_km`,
  `adjacency_matrix`, `wind_vector`, and `wind_weights`.
- Haversine distances in km with mean spherical Earth radius 6,371.0088 km,
  longitude wrapping, and rounding protection near antipodes.
- Symmetric Gaussian adjacency with an inclusive cutoff (default 20 km) and
  zero self-edges. Matrix indices preserve the caller's coordinate/station order.
- Meteorological FROM directions converted to east/north travel components.
  Wind compares the initial great-circle direction i to j with travel direction,
  then applies the section 5 multiplier with `min(speed_m_s / 5, 2)`.
- Explicit sigma and alpha parameters, range/finite-value checks, calm wind and
  alpha-zero behavior, and empty/single-node handling. Coincident nodes keep
  their base weight without directional enhancement. Missing wind is rejected.
- README usage, units, direction convention, parameter choices, and limitations.
  There are no new dependencies, environment settings, CLI targets, or data writes.

### Files changed in task 4

- Implemented `src/ecoproof/graph/geo.py`.
- Updated `src/ecoproof/graph/__init__.py`.
- Added `tests/test_geo.py` with 59 cases, including parameterized cases.
- Updated `README.md` and this progress file.
- `.env` and `.env.example` required no changes. No secrets, commits, or pushes
  were added. Existing repository files remain uncommitted.
- Read `AGENTS.md` and `docs/SPEC.md` fully before working. The spec was not
  modified; its SHA-256 remains
  `8307cf224dc66ca6767b0842817fbe4f37ef4d830ab2572c778edb79880f2395`.

### Tests run and actual results

Windows, existing Python 3.11 environment and pytest 9.1.1. Both final commands
exited 0:

```text
> .\.venv\Scripts\python.exe -m pytest -q tests/test_geo.py
...........................................................              [100%]
59 passed in 0.35s

> .\.venv\Scripts\python.exe -m pytest -q
........................................................................ [ 43%]
........................................................................ [ 87%]
....................                                                     [100%]
164 passed in 13.46s
```

The new cases cover analytical known spherical distances, symmetry, near
antipodes, longitude wrap, Gaussian decay, inclusive cutoff, zero self-edges,
colocated/empty/single-node graphs, all cardinal FROM directions including 360°,
oblique wind, direction at high latitude, downwind versus upwind edges, crosswind,
calm conditions, alpha zero, speed saturation, cutoff preservation, and invalid
coordinates/parameters/weather. All graph inputs in these tests are synthetic.

The first graph run returned `1 failed, 58 passed, 2 warnings in 1.02s`. The
failure was an insufficiently precise high-latitude destination fixture. Replaced
its manually specified coordinate with a destination calculated by the independent
spherical direct equations. The warnings were Windows access denials for pytest's
existing cache. Approved execution outside the sandbox allowed the final runs
above to complete without those warnings.

Executed the actual graph code block extracted from README and independently
queried the existing database read-only. Output:

```text
README graph example: assertions passed
OpenAQ key configured: False
silver.stations: 0
silver.readings: 0
silver.weather: 168
```

The original real Bronze weather file remains unchanged, SHA-256:
`89e91f8509e7c9a720e0430b592a57410d1c5733be363274edf79df9457283c3`.

### Uncertainties, choices, and deadline risk

- The spec does not choose sigma or a tuned alpha. Both are required arguments;
  README example values are illustrative, not evaluated or tuned settings. The
  speed response uses the spec's suggested bounded function with m/s inputs.
- A station-to-station direction is the initial great-circle bearing in the
  source station's local east/north plane. This follows the specified i-to-j
  orientation. The weights are generally asymmetric and are not row-normalized.
- Haversine uses a spherical approximation. Coincident and antipodal bearings
  are undefined, so they receive no directional boost. Antipodal edges are far
  outside the default city cutoff.
- This is a graph library for one regional weather observation per call. Time
  alignment, usable-neighbor counts, expected values, residuals, baseline scale,
  low-confidence flags, and classification remain task 5.
- Real station availability and the 8–10-station/seven-day milestone remain
  unverified because OpenAQ is still unconfigured. This is a deadline risk for
  today's full-week classification target and tomorrow's evaluation. Graph tests
  establish mathematical behavior, not detection performance on real air data.

### Next task

**Task 5, after user review:** implement `detect/classifier.py` per section 5,
including expected values, robust residual scale, z-scores, low-confidence
handling, and synthetic classification cases. Update progress and stop for review.
Real OpenAQ ingestion and coverage validation remain necessary before claiming
full-week classification on real readings.

## Task 5 — robust classifier and Gold output

Date: October 20, 2026. Status: **implemented and tested; user authorized task 6**.
The entry below records the task 5 handoff. No real air classification or
evaluation metrics were claimed.

### What was built

- Hourly classification with wind-weighted expected values, signed residuals,
  robust baseline sigma (`1.4826 * MAD` with an explicit floor), and absolute z.
  Missing neighbors are excluded and weights renormalized. Zero values remain
  usable. Baseline fitting uses only an explicitly selected earlier window.
- Low-confidence handling for fewer than two neighbors, missing weather, sparse
  baseline, missing follow-up/recent evidence, and conflicting neighbor behavior.
  These cases retain `VALID` with a reason, rather than asserting sensor health.
- Suspected isolated anomalies, five-hour persistent drift, and flat/stuck/zero
  checks with safeguards against steady neighborhoods and trailing spike effects.
- Plume evidence using FROM-to-travel direction, downwind geometry, station-local
  recent baselines, and a 1–3-hour lag consistent with distance / wind speed.
  Source and receiving observations are linked. A receiving station without
  further downstream evidence is not falsely labeled an isolated fault.
- An offline Silver-to-Gold builder. Interval-ending samples are explicitly
  averaged into UTC hours; missing hours are not filled. Parquet and DuckDB views
  save the spec's classified columns and a companion confidence/evidence dataset.
  Hash and batch fields remain null; provenance is not implemented in this task.
- `make detect ARGS="..."` with explicit baseline/output windows, sigma, and alpha.
  `--rebuild-silver` rebuilds Silver from Bronze first, giving a single-command
  offline rebuild. Atomic Gold view publication retains previous builds on failure.
- Build reports with actual row/label/confidence counts, baseline details, coverage,
  and warnings. These are run diagnostics, not precision, recall, or F1.
- Documentation of assumptions, threshold choices, retrospective timing, honest
  label interpretation, and a proposed confidence-field clarification to the spec.

### Files changed in task 5

- Implemented `src/ecoproof/detect/classifier.py` and `src/ecoproof/transform/gold.py`.
- Added `src/ecoproof/detect/__main__.py`; updated `src/ecoproof/detect/__init__.py`.
- Added public `wind_alignment` in `src/ecoproof/graph/geo.py` for plume geometry.
- Added `tests/test_classifier.py` (47 cases) and `tests/test_gold.py` (13 cases).
- Updated `Makefile`, `README.md`, `data/README.md`, `docs/SILVER.md`,
  `docs/INGESTION.md`, and this progress file. Added `docs/CLASSIFIER.md`.
- No dependency, lockfile, `.env`, or `.env.example` changes were needed. Detector
  parameters are CLI/config arguments; no new credentials or environment variables.
- No real-data Gold files, secrets, commits, or pushes were added. Synthetic data
  stays in test scratch directories. Existing source files remain uncommitted.
- Read `AGENTS.md` and `docs/SPEC.md` in full before work. The spec is unchanged,
  SHA-256 `8307cf224dc66ca6767b0842817fbe4f37ef4d830ab2572c778edb79880f2395`.

### Tests run and actual results

Windows, Python 3.11, pytest 9.1.1, DuckDB 1.5.6. Final full regression command,
exit 0:

```text
> .\.venv\Scripts\python.exe -m pytest -q
........................................................................ [ 32%]
........................................................................ [ 64%]
........................................................................ [ 96%]
........                                                                 [100%]
224 passed in 83.00s (0:01:23)
```

The final targeted command also exited 0:

```text
> .\.venv\Scripts\python.exe -m pytest -q tests/test_classifier.py tests/test_gold.py --durations=5
............................................................             [100%]
============================= slowest 5 durations =============================
15.53s call     tests/test_gold.py::test_end_to_end_output_confidence_region_isolation_and_rebuild
9.36s call     tests/test_gold.py::test_saved_plume_evidence_contains_real_computed_values
8.84s call     tests/test_gold.py::test_empty_window_preserves_previously_published_gold
8.37s call     tests/test_gold.py::test_one_command_rebuilds_from_synthetic_bronze
8.27s call     tests/test_gold.py::test_view_switch_rolls_back_both_views_and_preserves_batches
60 passed in 68.51s (0:01:08)
```

The 60 new cases exercise known weighted means/MAD, missing and invalid inputs,
threshold equality and both signs, baseline isolation, weather/neighbor gaps,
zero variance, spikes, drift, flatline and zero runs, regional rises, valid and
invalid plume transport, incomplete evidence, source/receiver links across output
windows, deterministic ordering, timezone normalization, and a synthetic seven-day
run with eight stations (1,344 classified fixture rows).

Storage checks execute real DuckDB/Parquet operations, not storage mocks: typed
round trips, saved confidence and source evidence, region isolation, unchanged
Silver files, deterministic rebuild contents, rollback of both views, preservation
of an existing test batch table, no empty replacement, explicit hourly averaging,
and the entire CLI path from synthetic Bronze through Silver to Gold.

Earlier runs and fixes:

- The initial classifier run reported `47 passed, 1 warning in 1.71s`; the warning
  was Windows denying pytest access to its existing cache. Subsequent approved
  execution outside the sandbox completed without cache warnings.
- The first combined run found two failures in the dense-graph plume negative
  control. The source was classified as a plume, but its receiver could still be
  called a fault. Added a second pass linking source evidence to receiving rows,
  preserving low confidence when no further downwind confirmation exists.
  Added output-window boundary checks and persisted source links. The final runs
  above include those fixes.
- That failed run reported `2 failed, 57 passed in 12285.79s (3:24:45)`. The cause
  of its unusually long elapsed time was not established. The final targeted run
  included duration reporting; its actual times are shown above.

Ran the actual Make target on the current real-data workspace:

```text
> .\.venv\Scripts\make.exe detect PYTHON=.venv/Scripts/python.exe "ARGS=--region delhi --baseline-start 2026-10-05T00:00:00Z --baseline-end 2026-10-06T00:00:00Z --start 2026-10-06T00:00:00Z --end 2026-10-12T00:00:00Z --sigma-km 10 --alpha 0.5"
.venv/Scripts/python.exe -m ecoproof.detect --region delhi --baseline-start 2026-10-05T00:00:00Z --baseline-end 2026-10-06T00:00:00Z --start 2026-10-06T00:00:00Z --end 2026-10-12T00:00:00Z --sigma-km 10 --alpha 0.5
No Silver stations for region 'delhi'; ingest OpenAQ and rebuild Silver first
make: *** [Makefile:25: detect] Error 1
```

The command exited nonzero and did not publish Gold. Independent read-only checks:

```text
OpenAQ key configured: False
silver.stations: 0
silver.readings: 0
silver.weather: 168
Local Gold builds: 0
```

`make help` also ran successfully. The real Bronze weather file remains unchanged:
SHA-256 `89e91f8509e7c9a720e0430b592a57410d1c5733be363274edf79df9457283c3`.

### Uncertainties, implementation choices, and deadline risk

- The spec requires low-confidence flags but omits their storage fields. The
  listed `gold.classified` schema is preserved; `gold.classification_evidence`
  stores flags, reasons, scale/smoothing, and plume evidence/source links.
  **Proposed clarification:** add `low_confidence BOOLEAN NOT NULL` and
  `reason TEXT NOT NULL` to `gold.classified`, and explicitly allow low-confidence
  `VALID` for incomplete/conflicting evidence. No edit to the spec was made.
- Defaults for the noise floor, sample minimum, recent-reference length, flatline
  evidence, and travel-time tolerance are documented provisional choices. They
  have not been tuned on real readings. The baseline is selected by the caller;
  the code cannot independently establish that it is healthy.
- Plume classification is retrospective and uses up to three later hours.
  Source-time regional wind and spherical straight-line travel are approximations.
  `VERIFIED_PLUME_EVENT` is the specified label, not external verification. Fault
  reasons explicitly say suspected; an isolated local source can look similar.
- Hourly averages are sample means, not duration-weighted means. No interpolation
  occurs. Input cadence, long intervals, station coverage, and baseline quality
  require inspection when real OpenAQ data is available.
- Consumers must join confidence/evidence to labels. A low-confidence `VALID`
  row is not proof of health and must not silently enter validated-only anchoring.
  The optional Silver rebuild and subsequent Gold publication are separate
  transactions; a failed detection can leave newly rebuilt Silver with prior Gold.
- The OpenAQ key remains absent, so the 8–10-station/seven-day real-data milestone
  and today's full-week real classification target remain unverified. A full
  seven-day output needs an earlier baseline and later plume context as well.
  This is a deadline risk for task 6's evaluation on copies of real readings.

### Next task

**Task 6, after user review:** implement `detect/inject.py` and `detect/evaluate.py`,
including stuck/zero, spike, drift, a lagged plume negative control, the naive
threshold baseline, and generated `reports/eval.json` plus a chart. Use copies of
real clean readings for the reported experiment and clearly identify synthetic
faults. Real data must be obtained before claiming those evaluation results.
Update progress and stop for review.

## Task 6 — injection evaluator and report/chart generation

Date: October 21, 2026 (started October 20). Status: **implementation tested;
real-data evaluation blocked**. The user subsequently authorized moving to task 7.
The requested experiment is not complete because the OpenAQ key and real air
observations are still absent. The project report explicitly records that state.

### What was built

- Independent copy-based stuck, zero, spike, additive drift, multiplicative
  degradation, and lagged plume injections. Source readings and baseline rows
  remain untouched. Missing samples and out-of-range values are not filled or
  clipped; intervention truth includes coincident unchanged samples in a fault
  window, while wholly unobservable interventions are rejected.
- Plume recipients selected by downwind geometry, observed timestamps, and
  distance/speed-consistent 1–3-hour lags, with smaller neighbor rises.
- Reproducible candidate selection by coverage, geometry, and a local seeded RNG.
  Selection does not use classifier outcomes. Each case starts from the same
  original input, and baseline calibration is checked for invariance.
- Per-case and per-type confusion counts, precision, recall, F1, and false-positive
  rates versus the strict `PM2.5 > 150` baseline. Low-confidence fault misses count
  as false negatives; confidence coverage is separately reported. Undefined
  ratios remain null. An unchanged control and plume false-alarm results are
  explicit, with no field-accuracy claims from unlabeled background observations.
- `make eval ARGS="..."`, an input fingerprint, saved original/injected values,
  rejection diagnostics, parameter recording, and JSON reports. Failed plume
  controls remain in completed reports and cause a nonzero CLI exit; the code
  does not retry cases to obtain better outcomes.
- Headless Matplotlib charts generated from report JSON, with separate precision,
  recall, and F1 panels and plume-control context. Synthetic fixture plots are
  clearly labeled software tests. Missing-data charts contain no metric bars.
- Safe report publication: a completed chart precedes JSON publication; earlier
  charts remain available. Failed plotting preserves the previous report. A
  blocked later attempt does not overwrite an existing completed experiment.

### Files changed in task 6

- Implemented `src/ecoproof/detect/inject.py` and `src/ecoproof/detect/evaluate.py`.
- Added `src/ecoproof/detect/plot.py`.
- Exposed the existing read-only Silver loader as `read_silver_inputs` in
  `src/ecoproof/transform/gold.py` for consistent detector/evaluator inputs.
- Added `tests/test_inject.py` (17 cases) and `tests/test_evaluate.py` (12 cases).
- Updated `Makefile`, `pyproject.toml`, `uv.lock`, `README.md`, `docs/CLASSIFIER.md`,
  and this progress file. Added `docs/EVALUATION.md` and `reports/README.md`.
- Generated `reports/eval.json` with blocked status and
  `reports/eval-4872559a7ea74fd6b531d64b19f8fed5.png`, which says evaluation was not run.
  These are availability/status artifacts, not measured performance results.
- Matplotlib 3.11.2 and its dependencies are locked. The Python 3.11 environment
  uses NumPy 2.4.6 and Pillow 13.0.0. No new `.env` settings or credentials were
  introduced; `.env.example` needed no change. No secrets, commits, or pushes.
- Ignored local files include the verified wheel cache, Matplotlib cache, and a
  synthetic chart reviewed under `.cache/chart-review/`. Synthetic test metrics
  were not copied to the project's evaluation report.
- Read `AGENTS.md` and the full spec before work. `docs/SPEC.md` is unchanged,
  SHA-256 `8307cf224dc66ca6767b0842817fbe4f37ef4d830ab2572c778edb79880f2395`.

### Tests run and actual results

Windows, Python 3.11, pytest 9.1.1, DuckDB 1.5.6, Matplotlib 3.11.2. Final full
suite, exit 0:

```text
> .\.venv\Scripts\python.exe -m pytest -q
........................................................................ [ 28%]
........................................................................ [ 56%]
........................................................................ [ 85%]
.....................................                                    [100%]
253 passed in 84.56s (0:01:24)
```

Earlier targeted run, exit 0:

```text
> .\.venv\Scripts\python.exe -m pytest -q tests/test_inject.py tests/test_evaluate.py
............................                                             [100%]
28 passed in 28.71s
```

The final suite adds the default three-cases-per-type denominator check to those
28 cases. Before chart installation completed, the injection and five computational
evaluation tests also ran successfully: `22 passed in 7.93s`. No new test failed.

New checks cover exact injection transforms, copy/baseline immutability, truth
mask boundaries, absent observations, out-of-range/no-effect rejection, plume
direction/lag/decay, known confusion ratios, null denominators, strict threshold
equality, low-confidence misses, reproducibility under reordered input, different
seeds, eight-station/seven-day input requirements, impossible plume controls,
preservation of deliberately failing control outcomes without reselection,
default aggregate denominators, actual PNG/JSON generation, failure cleanup,
preservation of completed reports, missing-data status, and CLI failure exits.

All numerical evaluation fixtures are synthetic and explicitly identified. Their
computed charts can show missed faults and false fault calls; no detector tuning
or headline performance claims were made from these software fixtures.

Ran the real Make target against the current workspace, nonzero exit:

```text
> .\.venv\Scripts\make.exe eval PYTHON=.venv/Scripts/python.exe "ARGS=--region delhi --baseline-start 2026-10-04T00:00:00Z --baseline-end 2026-10-05T00:00:00Z --start 2026-10-05T00:00:00Z --end 2026-10-12T00:00:00Z --sigma-km 10 --alpha 0.5 --seed 42"
.venv/Scripts/python.exe -m ecoproof.detect.evaluate --region delhi --baseline-start 2026-10-04T00:00:00Z --baseline-end 2026-10-05T00:00:00Z --start 2026-10-05T00:00:00Z --end 2026-10-12T00:00:00Z --sigma-km 10 --alpha 0.5 --seed 42
{
  "status": "blocked",
  "reason": "No Silver stations for region 'delhi'; ingest OpenAQ and rebuild Silver first",
  "report": "C:\\Users\\arfar\\Downloads\\FYP Project\\Hackathon IEEE\\reports\\eval.json",
  "chart": "C:\\Users\\arfar\\Downloads\\FYP Project\\Hackathon IEEE\\reports\\eval-4872559a7ea74fd6b531d64b19f8fed5.png",
  "case_count": 0,
  "plume_negative_control_passed": null
}
make: *** [Makefile:29: eval] Error 1
```

The saved report has `metrics: null`, an empty case list, and no plume verdict.
Visually inspected that status chart and a separately computed chart labeled
`SYNTHETIC FIXTURE — software test only`. The latter stayed in ignored cache.

Immediately before the project evaluation, read-only checks returned:

```text
OpenAQ key configured: False
silver.stations: 0
silver.readings: 0
silver.weather: 168
```

The original Bronze weather file is unchanged, SHA-256:
`89e91f8509e7c9a720e0430b592a57410d1c5733be363274edf79df9457283c3`.

### Installation issues and documentation checks

- The initial `uv add "matplotlib>=3.9,<4"` attempt failed because the sandbox
  could not access uv's cache. Approved execution resolved the lockfile but waited
  on large downloads. Public ranged-download probes succeeded, so the stalled
  install was interrupted.
- Downloaded only compatible wheel URLs recorded in `uv.lock` into the ignored
  workspace cache, and verified every wheel's SHA-256 against that lockfile.
  Installed those local wheels with `uv pip install --no-index --find-links
  .cache/wheels matplotlib==3.11.2`, then successfully ran `uv sync --locked
  --offline`. The environment matches the lockfile; no insecure TLS option or
  unverified dependency source was used.
- Checked Matplotlib 3.11.2's bundled configuration/cache documentation and source
  for `MPLCONFIGDIR` and its Windows default. Plotting uses the workspace cache
  when that setting is absent and restores the environment afterward. PNG rendering
  and saved-report content were exercised in tests and visually inspected.

### Uncertainties, remaining work, and deadline risk

- The required real-data experiment remains blocked. Requested that the user
  add `OPENAQ_API_KEY` to local `.env` and reply ready, without sharing the secret
  in chat. The key was still absent at the final data check. Neither real station
  density nor clean baseline/weekly coverage has been established.
- The proposed example uses October 4 as baseline, October 5–11 as output, and
  later observations on October 12 for plume context. Ingest and inspect that
  longer period after confirming a suitable station catalog, then rebuild Silver.
- Eligibility favors station windows with adequate baseline, source/weather
  history, and at least two complete neighbors. Results will not characterize
  all sparse or missing-data conditions. Eligibility and injection rejection
  counts are included so this restriction is visible.
- Original observations are only presumed healthy. Untouched negatives have no
  independently verified fault labels. Reused background across independent
  injection copies and small default case counts limit statistical conclusions.
- Amplitudes, durations, decay, and classifier parameters are provisional and
  untuned. No parameter search or selection based on test success occurs. A plume
  control passing the fault test does not alone prove affirmative plume detection;
  source labels and confidence are reported separately.
- Report/PNG generation and synthetic acceptance tests are implemented, but no
  real precision, recall, F1, control verdict, or measured improvement can be
  reported yet. This is a deadline risk for the October 25 submission; evaluation
  is a required feature and must not be replaced by fixture scores.

### Next task

Finish the real-data portion of **task 6** when the key and observations are
available: validate region/baseline/coverage, run evaluation, and review every
case and the plume negative control. After user review, the next implementation
task is **task 7: Merkle construction, canonical hashing, inclusion proofs, and
tampering/odd-count/single-leaf/reordering tests**. No task 7 code was started here.

## Task 7 — canonical records, Merkle trees, and inclusion proofs

Date: October 21, 2026. Status: **complete; user subsequently authorized task 8**.
The user authorized this task after task 6. Task 6's real-data experiment is still pending.

### What was built

- A strict twelve-field canonical payload: the ten Gold data columns plus
  `low_confidence` and `reason` from the evidence view. Derived `record_hash` and
  `batch_id` are excluded. Missing/extra fields and invalid types are rejected.
  No Gold schema or spec change was made.
- Compact, sorted UTF-8 JSON, fixed four-decimal numeric fields, decimal half-even
  rounding, normalized negative zero, explicit nulls, and UTC ISO timestamps with
  six fractional digits. Equivalent numeric types and timezone offsets canonicalize
  identically. Naive timestamps, nonfinite numbers, invalid Unicode, and silently
  truncated timestamp precision are rejected.
- SHA-256 with the spec's recommended `0x00` leaf and `0x01` parent prefixes.
  Parents concatenate raw 32-byte hashes. Trees sort by `(station_id, UTC ts)`,
  duplicate the last node at every odd level, reject empty/duplicate-key inputs,
  and support a single leaf with an empty proof. Immutable snapshots retain no
  mutable input mappings.
- Indexed inclusion paths and verification against a supplied trusted root and
  record count. Verification rejects malformed paths, inconsistent sides/indices,
  missing/extra steps, incorrect odd-node padding, and altered canonical payloads.
- A documented payload/byte/proof contract and a runnable synthetic example.
  No network, secrets, new dependencies, Gold materialization, or blockchain
  transaction is required by this library.

### Files changed in task 7

- Implemented `src/ecoproof/provenance/merkle.py`.
- Updated the status docstring in `src/ecoproof/provenance/__init__.py`.
- Added `tests/test_merkle.py` (82 cases).
- Added `docs/MERKLE.md`; updated `README.md` and this progress file.
- `.env.example` and dependency files needed no changes. No commits or pushes
  were made. Bronze, Silver, Gold, and the blocked evaluation report were not
  changed by this task; test fixtures are synthetic.
- Read `AGENTS.md` and the full spec before task work. The final spec hash is
  unchanged: `8307cf224dc66ca6767b0842817fbe4f37ef4d830ab2572c778edb79880f2395`.
  The original Bronze weather file also retains its prior hash:
  `89e91f8509e7c9a720e0430b592a57410d1c5733be363274edf79df9457283c3`.

### Tests run and actual results

Final full suite, Python 3.11 / pytest 9.1.1, exit 0:

```text
> .\.venv\Scripts\python.exe -m pytest -q
........................................................................ [ 21%]
........................................................................ [ 42%]
........................................................................ [ 64%]
........................................................................ [ 85%]
...............................................                          [100%]
335 passed in 97.07s (0:01:37)
```

This includes all 253 previous cases and 82 new Merkle cases. Checks cover exact
canonical UTF-8 bytes, numeric rounding/zero/null behavior, equivalent timestamps,
JSON round trips, domain separation/raw-byte concatenation, explicit three- and
six-leaf roots/paths, every proof for sizes 1/2/3/5/6/7/8/9/17, odd intermediate
levels, input permutations, duplicate keys, immutable snapshots, tampering with
each of the twelve payload fields, sibling/hash/side/order/index tampering, malformed
metadata, truncated/extra paths, and the need for a separately trusted count.

Earlier focused run, before adding the two large-decimal carry regressions:

```text
> .\.venv\Scripts\python.exe -m pytest -q tests/test_merkle.py
........................................................................ [ 90%]
........                                                                 [100%]
80 passed, 1 warning in 0.67s
```

The warning was `PytestCacheWarning: could not create cache path ...
.pytest_cache\v\cache\nodeids: [WinError 5] Access is denied`. The final full
suite ran with approved access to that existing cache and had no warnings.

During review, a separate manual probe with `Decimal('9' * 40 + '.99995')`
reproduced an edge-case failure, exit 1:

```text
InvalidOperation: [<class 'decimal.InvalidOperation'>]
```

Checked the installed standard-library `Decimal.quantize` documentation: it
signals `InvalidOperation` when the rounded coefficient exceeds context precision.
Allowed one additional integer digit for a rounding carry and added positive and
negative regression cases with exact Decimal JSON round trips. Both passed in the
final suite above. No failed case remains unresolved.

Executed the Python example extracted directly from `docs/MERKLE.md`, exit 0:

```text
record_count: 3
root: 4a268ccda76b4ec0489967f57f937549828142027b20b651ae3e05056c3428d6
original: True
tampered: False
```

That root is computed from three explicitly synthetic records. Changing `value`
from `12.5` to `12.5001` failed local verification. This is not a real-data batch,
an anchor, or a comparison with an on-chain root.

### Choices, uncertainties, and remaining limits

- The spec leaves the exact payload and rounding tie rule open. Chose the data
  columns plus confidence/reason, half-even rounding, and UTC microseconds;
  documented the choice without editing `docs/SPEC.md`. Confidence must not be
  lost when exporting records from the companion evidence view.
- Four-decimal canonicalization cannot detect every source-bit change. For
  example, `12.50001` and `12.5` produce identical canonical bytes; this behavior
  is documented and explicitly tested. Uncommitted fields, full evidence,
  detector parameters, and original Bronze bytes are outside this proof.
- Duplicate-last Merkle roots do not uniquely bind cardinality. `[a,b,c]` and
  `[a,b,c,c]` have the same root. Verification requires a trusted count as well as
  a trusted root; some paths can fit multiple counts. Task 8 must read both from
  the same registry batch, never trust metadata supplied with an uploaded proof.
- The generic tree includes every supplied record; it is not a sensor validator.
  Task 8's validated-data selection must join evidence and require `VALID` with
  `low_confidence = false`. Optional other-label batches must retain their labels
  and confidence. Skip empty hourly batches.
- Persisting `record_hash`/`batch_id`, hourly batch metadata, contract deployment,
  and submission/readback remain task 8. Gold hash/batch columns stay null until
  that integration. The module provides no new API endpoint.
- Real air observations and task 6's real evaluation are still unavailable from
  the preceding task. Do not replace that experiment with these fixtures or claim
  detector metrics, real anchors, or sensor truth from Merkle tests. The missing
  real-data/evaluation milestone remains a risk for the October 25 deadline.

### Next task

**Task 8, after user review:** implement `BatchRegistry.sol`, contract tests
including a duplicate-anchor revert, deployment tooling, and `anchor.py` with
hourly batch persistence and real root submission/readback. Acceptance requires
an actual testnet transaction hash. Keep credentials in local `.env`, document
needed settings in `.env.example`, and report any unavailable wallet/RPC/funding
or real-data prerequisites without inventing results. Task 6's real experiment
also remains pending until the OpenAQ key and suitable observations are available.
Stop here for review.

## Task 8 — registry, durable batch snapshots, and testnet client

Date: October 21, 2026. Status: **implementation tested locally; public-testnet
acceptance blocked; user subsequently authorized task 9**. The final full suite
passed after the JSON upload guard. No public transaction has been submitted.

### What was built

- The spec's `BatchRegistry.sol`: immutable owner, owner-only anchoring, write-once
  batch keys, stored root/window/count/time, and `BatchAnchored` events. Additional
  guards reject zero keys/roots, empty batches, and invalid windows. No spec edit.
- Hardhat 3.20.0, locked Solidity 0.8.20, compiler configuration, deployment artifact,
  and Solidity unit/fuzz tests. Compilation uses the npm compiler package and the
  Shanghai target. No separate compiler download or Forge dependency is required.
- Hourly confident-`VALID` selection from joined Gold/evidence, deterministic IDs
  containing the root, and immutable canonical snapshot rows in DuckDB. Empty
  hours are skipped; bad evidence or hashes roll back the requested preparation.
- Gold Parquet records now carry actual computed hashes. The DuckDB view resolves
  a batch link only for an identical committed hash, chooses one link if revisions
  overlap, and prefers mined batches. Rebuilds preserve prior proofs and metadata.
- `make anchor` subcommands `prepare`, `deploy`, `submit`, `read`, and `verify`, plus
  `contracts/script/deploy`. Public operations pin Ethereum Sepolia chain ID
  11155111. Deployment journals provide address lookup unless `REGISTRY_ADDRESS`
  explicitly overrides it. Read/verify require no private key.
- web3.py 7.16.0 signing using pending nonce, RPC gas/fee estimation, gas headroom,
  balance/chain/owner/code checks, and signed-intent persistence before broadcast.
  Retries recover the same transaction hash and bytes instead of creating another
  deployment or nonce after a lost response.
- Receipt status/hash/block checks, matching event and current registry readback,
  and database publication only after those checks pass. Current state plus the
  receipt event/header avoid an archive-RPC requirement for old submissions.
- Verification against the registry's root AND count. Edited canonical values
  fail; duplicate keys and non-object uploaded JSON are rejected. Provider error
  details are suppressed to avoid exposing credential-bearing URLs.

### Files changed in task 8

- Implemented `contracts/BatchRegistry.sol` and `contracts/script/deploy`; added
  `contracts/hardhat.config.ts`, `contracts/package.json`, `contracts/package-lock.json`,
  `contracts/src/Compile.sol`, and `contracts/test/BatchRegistry.t.sol`.
- Implemented `src/ecoproof/provenance/anchor.py`; added
  `src/ecoproof/provenance/batches.py`; updated the provenance package docstring.
- Updated `src/ecoproof/transform/gold.py`, `src/ecoproof/config.py`, `Makefile`,
  `pyproject.toml`, `uv.lock`, and `.env.example` (`REGISTRY_ADDRESS` added).
- Added `tests/conftest.py`, `tests/test_batches.py` (9 cases), and
  `tests/test_anchor.py` (20 cases after final upload regressions). Updated Gold
  expectations and added one registry-setting configuration test.
- Added `docs/ANCHORING.md`. Updated `contracts/README.md`, `README.md`,
  `docs/MERKLE.md`, `docs/CLASSIFIER.md`, `data/README.md`, and this progress file.
- `.env` was not changed; no wallet was generated for public use. Random test keys
  exist only in the local EVM test process and are never saved to `.env` or logged.
  No commits or pushes. Dependency/artifact caches are ignored, including an unused
  root `node_modules` from the initial tool setup; the active package is in `contracts/`.

### Tests run and actual results

Final full suite, Python 3.11 / pytest 9.1.1, exit 0. Includes all 335 prior cases
and 30 task 8 additions:

```text
> .\.venv\Scripts\python.exe -m pytest -q
........................................................................ [ 19%]
........................................................................ [ 39%]
........................................................................ [ 59%]
........................................................................ [ 78%]
........................................................................ [ 98%]
.....                                                                    [100%]
365 passed, 1 warning in 147.43s (0:02:27)
```

The preceding full suite passed before adding the four non-object JSON regressions:

```text
> .\.venv\Scripts\python.exe -m pytest -q
361 passed, 1 warning in 147.43s (0:02:27)
```

The warning comes from the web3 dependency importing `websockets.legacy`:
`DeprecationWarning: websockets.legacy is deprecated`. The application uses HTTP
RPC; the warning has not been hidden or treated as a failed transaction.

Final Solidity suite, from `contracts/`, exit 0:

```text
> npm.cmd test
> ecoproof-contracts@0.1.0 test
> hardhat test solidity

No contracts to compile

Running Solidity tests

  test/BatchRegistry.t.sol:BatchRegistryTest
    ✔ testOwnerAndStoredFields()
    ✔ testOnlyOwnerCanAnchor()
    ✔ testInvalidWindowsRejected()
    ✔ testFuzzRoundTrip(bytes32,bytes32,uint64,uint32) (runs: 256)
    ✔ testEmptyRootRejected()
    ✔ testEmptyKeyRejected()
    ✔ testEmptyBatchRejected()
    ✔ testDuplicateAnchorRevertsAndPreservesOriginal()
    ✔ testDifferentKeysAreIndependent()

  9 passing
```

The explicit deployable build also ran successfully:

```text
> npm.cmd run compile
> hardhat compile BatchRegistry.sol
Compiled 1 Solidity file with solc 0.8.20 (evm target: shanghai)
```

After correcting artifact generation, the focused anchoring suite returned:

```text
> .\.venv\Scripts\python.exe -m pytest -q tests/test_anchor.py -x
15 passed, 1 warning in 34.00s
```

Later checks added the journal-write-failure guard and four JSON top-level type
regressions. Local EVM tests cover signed deployment, code/owner/receipts, real
event/root/count readback, edited-record failure, duplicate transaction status 0,
idempotent retries, interruptions before send and after mining, failed readback,
wrong chain/nonowner/empty code, changed registry, corrupt signed intent, and
secret-safe CLI errors. Storage tests cover hourly selection, empty hours,
confidence exclusion, old-proof retention after changed/reordered Gold rebuilds,
view row uniqueness, atomic rollback, and corrupt snapshot rejection.

These fixtures are explicitly synthetic and use a short-lived local chain ID
31337. Their transaction hashes are not Sepolia hashes or public acceptance evidence.

### Real workspace checks and blocked commands

Ran the actual Make preparation target, exit 1:

```text
> .\.venv\Scripts\make.exe anchor PYTHON=.venv/Scripts/python.exe "ARGS=prepare --start 2026-10-05T00:00:00Z --end 2026-10-12T00:00:00Z"
.venv/Scripts/python.exe -m ecoproof.provenance.anchor prepare --start 2026-10-05T00:00:00Z --end 2026-10-12T00:00:00Z
{
  "status": "blocked",
  "reason": "Gold classifications/evidence are missing; run make detect after ingesting air observations"
}
make: *** [Makefile:33: anchor] Error 1
```

Ran the deployment wrapper, exit 1:

```text
> .\.venv\Scripts\python.exe contracts/script/deploy
{
  "status": "blocked",
  "reason": "RPC_URL is unset; configure an Ethereum Sepolia HTTP RPC in local .env"
}
```

Final prerequisite checks printed only presence/status, never credentials:

```text
rpc_url configured: False
private_key configured: False
openaq_api_key configured: False
public deployment journal exists: False
real-data evaluation status: blocked
```

Asked the user to add a funded throwaway Sepolia wallet's `PRIVATE_KEY` and
`RPC_URL` to local `.env` and reply ready, without sharing them in chat. No ready
response was received. There is no real Gold batch, deployment address, public
transaction hash, gas measurement, or explorer result to report.

Read `AGENTS.md` and the full spec before work. Rechecked unchanged SHA-256 values:

- `docs/SPEC.md`: `8307cf224dc66ca6767b0842817fbe4f37ef4d830ab2572c778edb79880f2395`.
- Original Bronze weather file: `89e91f8509e7c9a720e0430b592a57410d1c5733be363274edf79df9457283c3`.

### Issues found and resolved; documentation checked

- uv/npm initially could not write their existing caches. Approved installation
  completed and locked web3.py/Hardhat/solc. An npm invocation using `--prefix`
  looked in the wrong directory; running `npm ci` with `contracts/` as the working
  directory succeeded (`added 61 packages in 21s`).
- Hardhat initially scanned the entire root package for remappings and failed on
  the protected pytest cache. Moved the new tooling package into `contracts/`.
  A source directory of `.` then included dependency Solidity files; narrowed it
  to `src/` with an import of the required root-level registry file.
- Imported-only compilation did not emit the deployable registry artifact. The
  first Python integration run reported `1 failed, 33 passed, 1 warning, 11 errors
  in 108.52s (0:01:48)`, all failures/errors caused by that missing artifact.
  Explicitly building `BatchRegistry.sol` fixed it; the Python EVM fixture runs
  the same explicit compile before deployment.
- Final review found JSON `null` could be interpreted as the default stored-record
  choice. Added a strict object reader and four regressions instead of accepting
  non-object uploads.
- Checked official Hardhat configuration/testing docs and installed source;
  official web3.py GitHub transaction/contract/Eth documentation and installed
  signatures; and Ethereum's chain registry metadata for Sepolia. ReadTheDocs and
  ethereum.org returned HTTP 403 even with approved network access, so official
  source documentation was used. Links are recorded in `docs/ANCHORING.md`.

### Limits, uncertainties, and next task

- Public testnet acceptance is **not complete**. RPC/wallet/funding and real Gold
  data remain prerequisites. Task 6's real-data experiment is still blocked by
  absent OpenAQ observations; no synthetic metric or transaction substitutes for
  these required milestones. This remains a deadline risk for October 25.
- Added companion `gold.batch_records` and `gold.anchor_submissions` tables to
  retain proofs and signed intent without changing the spec's `gold.batches`
  columns. Back up those tables and deployment journals; deleting them is not a
  Gold rebuild operation. External transaction history is not derived from Bronze.
- A successful receipt/readback means mined inclusion, not irreversible finality.
  Later proof checks read the configured registry again. The verifier depends on
  the trusted chain/registry identity and RPC, and proves only canonical payload
  integrity, not sensor truth. Four-decimal precision limits still apply.
- One submitting process per wallet is required. The DB protects its own writer
  process, not an external wallet app or another data directory. Reverted or
  externally replaced transactions and orphaned on-chain keys need inspection;
  automatic fee replacement, event-history recovery, and multi-network operation
  are outside this MVP implementation.
- Finish task 8's public deployment and one real batch submission/readback when
  the prerequisites are supplied. Record only the actual receipt and explorer
  link then. **Task 9, after user review**, is the spec's FastAPI endpoints and
  response/verification tests. No task 9 implementation was started. Stop for review.

## Task 9 — FastAPI endpoints and record verification

Date: October 21, 2026. Status: **implemented and tested locally; user authorized
task 10 next**. The user authorized task 9 after task 8. Public-testnet and
real-air acceptance remain blocked by the earlier prerequisites; no public
transaction or real evaluation result is claimed.

### What was built

- All six non-stretch endpoints in spec section 8: `GET /stations`, `/readings`,
  `/events`, `/batches`, `/proof`, and `POST /verify`. Explicit response models
  generate OpenAPI schemas and reject inconsistent stored data.
- UTC timestamp validation and output, bound SQL parameters, a 31-day readings
  window, limited event/batch lists, stable ordering, confidence/reason fields,
  saved wind/plume evidence, and explicit null labels for stations without a
  current classification. Missing observations are never filled or fabricated.
- Short read-only DuckDB transactions. Serving never creates a database, builds
  views, prepares batches, deploys a contract, or submits a transaction. Database
  connections close before verification contacts RPC.
- Proof retrieval validates immutable snapshots. Default lookups follow the
  current Gold hash; an explicit batch ID retrieves retained history after a
  rebuild. Proofs include the canonical string, payload, leaf hash/index, sibling
  path, root, and batch metadata.
- Verification hashes the uploaded payload, rebuilds the saved path (or checks
  an optional supplied path), and reads the configured registry for root/count
  and window. It distinguishes verified, unanchored, batch mismatch, and record
  mismatch. Saved chain/registry bindings are enforced. The public client remains
  pinned to Sepolia; local tests inject their own isolated registry dependency.
- Exact decimal JSON parsing before four-decimal canonical rounding, rejection
  of duplicate keys/non-object uploads/coercions/non-finite numbers/extra fields,
  and a 64 KiB request limit. Canonical strings retain the exact committed bytes;
  ordinary response numbers are intended for display.
- Explicit missing-data/configuration errors and sanitized provider/filesystem
  failures. The API requires no private key, exposes no signing operations, and
  does not return raw signed transactions or authenticated RPC URLs.
- `make api` now invokes uvicorn on localhost:8000. Documentation starts without
  credentials or data. Added endpoint/filter/error/upload instructions and kept
  the frontend and stretch chat pending. `docs/SPEC.md` was not edited.

### Files changed

- `src/ecoproof/api/main.py` — application factory, routes, dependency injection,
  and exception handling.
- `src/ecoproof/api/models.py` — request/response schemas and exact numeric types.
- `src/ecoproof/api/store.py` — read-only snapshots, queries and proof projection.
- `src/ecoproof/api/requests.py` — bounded UTF-8 JSON parser and custom route hook.
- `src/ecoproof/api/__init__.py` — package description.
- `tests/test_api.py` — 52 API cases, including actual local-EVM integrations.
- `pyproject.toml`, `uv.lock` — FastAPI, uvicorn, and an explicit Pydantic v2
  dependency. Resolved 73 packages; installed FastAPI 0.156.2, uvicorn 0.54.0,
  Starlette 1.9.0, and retained Pydantic 2.14.1.
- `Makefile` — API target and help text.
- `.env.example` — explains that HTTP verification needs RPC/registry, not a key.
- `README.md`, `docs/API.md`, `docs/PROGRESS.md` — setup, API contract, limitations,
  and actual verification results.

Documentation downloads and the one-off uvicorn smoke helper/log are in ignored
`.cache/`. No generated air data, metrics, chain addresses, or public transactions
were added. Contract sources and existing pipeline tests were not changed.

### Tests run and actual output

Final required full Python suite, exit 0:

```text
> .\.venv\Scripts\python.exe -m pytest -q
417 passed, 2 warnings in 234.14s (0:03:54)
```

The two warnings were:

```text
DeprecationWarning: websockets.legacy is deprecated
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
```

They originate in dependency imports and were not hidden. FastAPI's official
testing documentation still uses HTTPX; installed Starlette supports it with a
deprecation warning. Existing HTTPX ingestion code remains unchanged.

Focused API suite before adding the final filesystem-error and default-chain/RPC
failure cases, exit 0:

```text
> .\.venv\Scripts\python.exe -m pytest -q tests/test_api.py -x
..................................................                       [100%]
50 passed, 2 warnings in 83.66s (0:01:23)
```

The final full run includes both subsequent cases. Tests cover timezone offsets
and half-open bounds, missing/empty data, low confidence, parameter binding,
event filters/evidence, unmined metadata, odd and single-leaf proofs, retained
snapshots after rebuild, corrupt snapshots, malformed uploads, decimal rounding
boundaries, and secret-safe errors. Local EVM tests deploy the real contract,
anchor synthetic snapshots, check actual registry roots/counts, reject edited
records/paths and incorrect on-chain counts, enforce registry binding, and check
that HTTP verification does not increment the wallet nonce. No public network
is used by those fixtures; chain ID 31337 is explicitly local.

The actual Make API target was also invoked with `ARGS=--help`, exit 0:

```text
> .\.venv\Scripts\make.exe api PYTHON=.venv/Scripts/python.exe "ARGS=--help"
.venv/Scripts/python.exe -m uvicorn ecoproof.api.main:app --host 127.0.0.1 --port 8000 --help
Usage: python -m uvicorn [OPTIONS] APP
```

### Actual HTTP smoke against the real workspace

Started the actual uvicorn module on an available localhost port in an owned
hidden subprocess, made HTTP requests, then stopped that process. Checked Swagger
UI HTML and OpenAPI responses; no interactive browser rendering is claimed.
The valid POST smoke body was explicitly synthetic and was rejected because no
real batches exist. It was not persisted or used as a substitute air record.

```text
> .\.venv\Scripts\python.exe .cache/api-smoke.py
GET /docs: 200 (Swagger UI HTML)
GET /openapi.json: 200 (6 MVP endpoints)
GET /stations: 200 []
GET /events: 503 {"detail": "Required data views are missing; complete the Silver/Gold build and batch preparation"}
GET /batches: 503 {"detail": "Required data views are missing; complete the Silver/Gold build and batch preparation"}
GET /proof: 503 {"detail": "Required data views are missing; complete the Silver/Gold build and batch preparation"}
GET /readings: 503 {"detail": "Required data views are missing; complete the Silver/Gold build and batch preparation"}
POST /verify: 503 {"detail": "Required data views are missing; complete the Silver/Gold build and batch preparation"}
Real database SHA-256 unchanged; owned uvicorn process stopped.
```

Prerequisite presence/status checks printed no credentials:

```text
RPC configured: False
OpenAQ key configured: False
Public deployment journal: False
Evaluation status: blocked
```

Rechecked unchanged SHA-256 values:

- `docs/SPEC.md`: `8307cf224dc66ca6767b0842817fbe4f37ef4d830ab2572c778edb79880f2395`.
- Original Bronze weather file: `89e91f8509e7c9a720e0430b592a57410d1c5733be363274edf79df9457283c3`.

### Issues resolved and documentation checked

- uv initially failed to access its existing cache; approved installation
  succeeded. The first pytest attempt also hit the protected existing cache:
  `4 warnings, 1 error in 6.90s`. Approved test execution resolved that access
  issue without deleting or moving project data.
- The first executing API run returned `1 failed, 22 passed, 2 warnings in
  34.07s`. The corruption test expected 409 from a default proof lookup, but a
  changed saved hash correctly removed the current Gold link and returned 404.
  The corrected test checks both that 404 and an explicit historical lookup's 409.
- The next run returned `1 failed, 46 passed, 2 warnings in 50.93s`. Its request
  helper shared the original proof's record dictionary, so a tampering test also
  changed its later comparison input. Copying that input fixed the test; the
  actual verifier had correctly rejected the edited payload.
- Checked official FastAPI response-model/testing/custom-request documentation,
  Pydantic strict number/Decimal serialization documentation, and installed
  `WithJsonSchema`/Starlette behavior. Corrected the generated numeric input schema
  so it does not advertise numeric strings that the canonical format rejects.
  Source links are in `docs/API.md`.

### Limits, uncertainties, and next task

- Task 9's local API acceptance is exercised, including real execution on a local
  EVM. **Real OpenAQ data, task 6's real-data evaluation, and task 8's public
  Sepolia deployment/anchor remain outstanding.** Do not present synthetic
  fixtures or local transaction hashes as meeting those requirements. This is
  still a deadline risk for October 25.
- The spec leaves wire shapes, limits, and historical selection unspecified.
  `docs/API.md` records the implemented choices: JSON object uploads, optional
  supplied paths, current-hash proof selection with explicit historical batch
  IDs, bounded lists, and distinct error/verification outcomes. No spec rewrite.
- Fault rows expose saved neighbor count/reason, wind context and any plume/source
  evidence. The detector does not persist a separate per-neighbor fault-measurement
  list; the API does not fabricate one. Low-confidence VALID is not verified healthy.
- Stop API readers during pipeline/anchoring writes because DuckDB does not allow
  external writers alongside active read connections. A lock conflict returns
  503. Public hosting/authentication and persistent database service architecture
  are outside this task.
- Verification still trusts the configured chain/registry identity and RPC. It
  establishes canonical payload integrity at four-decimal precision, not sensor
  truth or irreversible chain finality. RPC failure returns 503, never a local
  success fallback.
- **Next: task 10 after user review** — React/Vite/Leaflet map, station chart,
  batches/verify and metrics views against this API, with honest missing-data
  states. No task 10 or stretch chat work was started. Stop for review.

## Task 10 — React, Leaflet, record verification and evaluation views

Date: October 21, 2026. Status: **implemented and tested locally; awaiting user
review**. The user authorized the next task after task 9. The browser demo uses
an isolated synthetic fixture and actual local contract execution. Real air-data
evaluation and public Sepolia acceptance remain outstanding.

### What was built

- React/TypeScript/Vite frontend with Monitor, Verify and Evaluation navigation,
  responsive desktop/mobile layouts, accessible labels and keyboard selection.
- Leaflet station map with classification colors, selected wind arrow, searchable
  station list and disclosed tile failures. Missing classification and low
  confidence remain distinct from confident VALID. UTC observed/expected charts
  preserve gaps and can compare actual readings at a nearby station. Inspectors
  show saved wind, neighbor count, reason and fault/plume evidence.
- Saved-batch pagination, current or historical proof lookup, canonical JSON,
  leaf hash/root and ordered inclusion path. The record editor and JSON file input
  preserve raw numeric text for the backend. Edits clear verdicts and abort/ignore
  stale responses. Verified, mismatched, unanchored and unavailable outcomes are
  distinct. Only valid Sepolia transaction metadata gets a public explorer link;
  local chain 31337 is labeled explicitly.
- Evaluation reads the existing report and referenced PNG. A narrow Vite plugin
  serves those assets in development and copies their exact bytes into the build.
  Blocked reports show their real status chart and no metric table. Completed
  report rendering preserves undefined ratios and labels synthetic interventions.
- Vite dev/preview forwards `/api/*` to the six existing FastAPI routes. The
  optional `ECOPROOF_API_ORIGIN` is a local, server-only process setting. Root
  `.env` is not loaded by Vite; credentials must never go into `VITE_*` variables.
  `make web` now starts the frontend on localhost:5173.
- Browser acceptance runs through pytest against an owned FastAPI server, built
  frontend, isolated DuckDB fixture and actual local EVM. It checks that browser
  verification does not change the wallet nonce and stops its owned services.
  No synthetic observations were written to the real database.

### Files changed

- `web/package.json`, `web/package-lock.json`, `web/tsconfig.json`,
  `web/vite.config.ts`, `web/index.html` — locked tooling, build and local proxy.
- `web/src/App.tsx`, `main.tsx`, `api.ts`, `types.ts`, `domain.ts`,
  `components.tsx`, `styles.css` — navigation, data fetching, display rules and UI.
- `web/src/Monitor.tsx`, `StationMap.tsx`, `StationDetail.tsx`, `ReadingChart.tsx`,
  `Verify.tsx`, `Evaluation.tsx` — the three views and their components.
- `web/scripts/reports.ts` — restricted evaluation asset serving/copying.
- `web/src/domain.test.ts`, `web/scripts/reports.test.ts` — 14 unit checks.
- `web/playwright.config.ts`, `web/browser/app.spec.ts`, `tests/test_web.py` —
  nine browser cases under one Python integration test.
- `Makefile`, `.gitignore`, `.env.example`, `README.md`, `web/README.md`,
  `docs/API.md`, `docs/PROGRESS.md` — commands, ignored outputs and documentation.

No backend endpoint, pipeline, contract, spec, Bronze file, or evaluation result
was changed. Generated frontend assets, browser screenshots/traces/raw output,
documentation downloads and one-off smoke helpers remain ignored.

### Tests run and actual output

Final required full Python suite, including the browser integration, exit 0:

```text
> .\.venv\Scripts\python.exe -m pytest -q
418 passed, 2 warnings in 288.77s (0:04:48)
```

The warnings remain the existing dependency deprecations:

```text
DeprecationWarning: websockets.legacy is deprecated
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
```

Frontend unit tests from `web/`, exit 0:

```text
> npm.cmd test
> vitest run
Test Files  2 passed (2)
Tests  14 passed (14)
Duration 1.40s (tests 63%, transform 18%, import 16%, worker 3%)
```

Checks cover classification/confidence, wind direction, geographic comparison,
chart gaps, exact decimal/duplicate-key upload text, explorer links, report
validation/null ratios, copied report bytes, traversal rejection and PNG checking.

Final TypeScript check and production build from `web/`, exit 0:

```text
> npm.cmd run build
> tsc --noEmit && vite build
vite v8.3.4 building client environment for production...
✓ 27 modules transformed.
✓ built in 691ms
```

Focused browser integration after fixing keyboard selection, exit 0:

```text
> .\.venv\Scripts\python.exe -m pytest -q -s tests/test_web.py
Running 9 tests using 1 worker
9 passed (31.3s)
1 passed, 1 warning in 63.53s (0:01:03)
```

The nine cases exercise keyboard map selection, nearby series/wind, event
filtering/evidence, real single/odd-leaf inclusion, edit failure and restoration,
decimal precision, stale-response rejection, actual HTTP validation errors,
explicit service-failure fixtures, empty data, the published evaluation chart,
and mobile navigation without horizontal page overflow. Browser JavaScript
errors fail the checks. Successful verification calls execute against the actual
local EVM; only selected failure states are intercepted. OSM tiles are blocked
in these tests to exercise the disclosed fallback. UTF-8 browser output is saved
in `web/test-results/browser-output.txt`; the focused run also emitted Node's
`NO_COLOR`/`FORCE_COLOR` warning. It was not hidden.

The Make target was invoked successfully:

```text
> .\.venv\Scripts\make.exe web "ARGS=--help"
npm.cmd --prefix web run dev -- --help
vite/8.3.4
```

### Browser smoke against the actual workspace

Started the real read-only API and built frontend on owned temporary localhost
ports, opened headless Chrome, then stopped them. No data API response was mocked.

```text
> .\.venv\Scripts\python.exe -m pytest -q -s .cache/test_web_smoke.py --basetemp=.cache/web-smoke-tmp
Monitor: 0 actual stations; no synthetic fallback.
Verify: batches HTTP 503; no fabricated verification verdict.
Evaluation: blocked; referenced report chart rendered.
Mobile: 390px viewport, no page overflow.
Browser JavaScript errors: 0.
Real database SHA-256 unchanged; owned servers and browser stopped.
1 passed, 1 warning in 16.80s
```

Inspected desktop/mobile screenshots of the fixture and real empty/blocked UI.
Final prerequisite checks printed only presence/status, never credentials:

```text
RPC configured: False
OpenAQ key configured: False
Evaluation status: blocked
Copied report matches: True
```

The spec SHA-256 remains
`8307cf224dc66ca6767b0842817fbe4f37ef4d830ab2572c778edb79880f2395`;
the original Bronze weather SHA-256 remains
`89e91f8509e7c9a720e0430b592a57410d1c5733be363274edf79df9457283c3`.
Git ignores `.env`, frontend dependencies/builds, browser output and `.cache`.

### Issues resolved and documentation checked

- npm initially hit its protected cache; approved installation succeeded with
  51 packages added, 52 audited, and zero reported vulnerabilities at install.
- Initial builds found an extra CSS parenthesis. Corrected the property and
  formatted the stylesheet. Added the explicit `.ts` config import supported by
  the checked tooling, resolving Vite's warning about future config loading.
- The initial unit run had two failures because its temporary cache parent did
  not exist (`2 failed | 12 passed`). Creating that test directory fixed both.
- The first browser run had seven passes and two failures: marker labels were
  assigned before Leaflet created icons, and an event-filter locator was wrong.
  Printing Unicode browser output also failed under Windows cp1252; exact output
  is now saved as UTF-8 and the console receives an escaped copy.
- The next run had `2 failed, 7 passed (55.6s)`: Leaflet's default Enter key opened
  a popup without selecting the chart, and an event heading matched two elements.
  Added explicit Enter/Space chart selection and a precise heading locator. All
  nine cases then passed, followed by the full repository suite above.
- Checked npm versions/engines, official Vite proxy/plugin docs, React effect
  cleanup, Playwright browser channels, Leaflet's version 1.9.4 quick start and
  installed keyboard/popup source. Links are in `web/README.md`.

### Limits, uncertainties, and next task

- **Real air observations, task 6's measured real-data experiment, and task 8's
  public Sepolia deployment/anchor remain blocked.** The full real-data demo is
  not accepted by local synthetic tests. This remains an October 25 deadline risk.
- The completed-report table has schema/unit checks; browser rendering exercised
  the actual blocked report because no completed real-data report exists. Live
  OSM tile delivery and a public explorer transaction were not validated here.
- Nearby chart comparisons use same-cluster coordinates within 20 km; they are
  labeled geographic context because the API does not expose the exact detector
  graph. Saved fault evidence does not invent per-neighbor measurements.
- Production/preview report assets are a build snapshot: rebuild after an
  evaluation. Local dev/preview needs the API running. Public hosting is outside
  this task. Stop API readers while pipeline/anchoring writers use DuckDB.
- Browser tests now require the built frontend and installed Chrome (documented
  alternatives exist). No browser tooling requirement is silently skipped.
- **Next listed task: 11, stretch guarded SQL chat, only after user review.**
  Prioritize the blocked real-data/public-chain MVP milestones before stretch
  work. No task 11 implementation was started. Stop for review.

## October 23 — real-data pipeline and running submission demo

Status: **application running locally with real data; public anchoring unfunded;
measured plume-control acceptance failed**. The user authorized doing the work
needed to run the application and show actual output for submission. No stretch
chat or AWS migration was added, and no external submission/publication occurred.

### What was built and executed

- Confirmed the newly saved OpenAQ key with an actual catalog request: 94 Delhi
  locations. Confirmed the RPC reports Ethereum Sepolia chain ID 11155111.
- Generated a dedicated wallet with the installed `eth_account.Account.create`
  and saved its private key directly to ignored root `.env`. The key was never
  printed. Public address: `0x94Da0DeC6446de596296552196586A5eB2cC6291`.
  Repeated actual RPC checks found a zero test-ETH balance. Requested faucet
  funding from the user while continuing all independent work.
- Ingested October 4–12 data for 12 nearby candidate locations: 6,759 raw readings
  and 216 weather hours. Initial bounded Silver retained 6,749 readings, excluded
  10 boundary rows, rejected zero invalid rows, and reported ten locations with
  observations on all nine dates. The two sparse candidates remain visible.
- The one-day calibration had only 15–23 usable hourly observations per station,
  below the unchanged minimum of 24. Ingested October 3 as an earlier baseline
  day, adding 837 raw readings and 24 weather hours. The final unbounded rebuild
  contains 7,596 readings, including provider interval-ending boundary records,
  94 catalog locations and 240 weather hours. Original Bronze files were retained.
- Ran detection with October 3–4 calibration and October 5–11 output, plus later
  context. It produced 1,546 hourly rows at 11 stations: 1,514 VALID, 15 suspected
  faults and 17 rows with plume evidence. There are 257 low-confidence rows within
  VALID. Prepared 1,257 confident VALID records into 165 hourly batches.
- Ran the 18-case injection experiment on copies of the real Silver data. The
  report and figure contain the actual measured weak scores and a failed plume
  negative control. No scored cases were discarded, no thresholds were retuned,
  and no observations were fabricated to improve the result.
- Started the API at localhost:8000 and Vite at localhost:5173 as owned hidden
  background processes, verified their HTTP responses, and opened the dashboard
  in the user's browser. They are intentionally left running. Launcher PIDs and
  logs are recorded in `.cache/demo-runtime.json` and `.cache/demo-*.log`.
- Executed a separate real-workspace browser walkthrough, with no data-response
  mocks: map tiles, current station selection, nearby chart, saved proof, actual
  unavailable-chain response, completed evaluation table/chart and mobile view.
  Saved actual screenshots and a machine-readable browser result in `reports/`.
- Added the real-data demo guide, a factual submission description draft and MIT
  software license. Data providers retain their own attribution/license terms.

### Code fixes made during the real run

- `src/ecoproof/transform/silver.py` and `gold.py`: wrap in-memory bulk inserts
  in explicit transactions, retaining all existing constraints and atomic view
  publication. The first full Silver run exposed the cost of per-row commits.
  Original and transaction-wrapped bounded builds both completed with identical
  counts/rejections. No unmeasured speedup factor is claimed.
- `web/src/Monitor.tsx`: default to a station that has classified observations
  when the catalog's first entry is historical/empty. Explicit selections still
  work for every catalog station.
- `tests/test_web.py`: put an unobserved station first in API sort order, matching
  the real catalog condition. Existing browser navigation/initial-chart checks
  now exercise this regression.

An attempted identity-checked stop of the original slow build hit sandbox WMI
access denial. The approved retry found that the original process had finished,
so no process was stopped. The earlier and later persistent builds were kept.

### Files changed

- Code/tests: the four files named above.
- Setup and usage: `README.md`, `web/README.md`, `data/README.md`,
  `docs/INGESTION.md`, `docs/EVALUATION.md`, `docs/ANCHORING.md`,
  `reports/README.md`, `docs/PROGRESS.md`.
- Added `docs/DEMO.md`, `docs/SUBMISSION.md` and `LICENSE`.
- Generated `reports/eval.json`,
  `reports/eval-c913e0bbc643443d8be95d2374b05210.png`, `reports/demo-monitor.png`,
  `reports/demo-verify.png`, `reports/demo-evaluation.png`,
  `reports/demo-mobile.png`, and `reports/demo-browser.json`.
- Ignored local state: `.env`, new immutable Bronze snapshots, Silver/Gold builds,
  DuckDB batch snapshots, frontend build, browser output and `.cache` helpers/logs.
  `.env.example` already documents every setting used; no new setting was needed.

### Tests and real output

Full required suite after the code fixes, exit 0:

```text
> .\.venv\Scripts\python.exe -m pytest -q
418 passed, 2 warnings in 288.94s (0:04:48)
```

The warnings remain `websockets.legacy` deprecation and Starlette's HTTPX
TestClient deprecation. Neither was hidden.

Frontend unit checks, exit 0:

```text
> npm.cmd test
Test Files  2 passed (2)
Tests  14 passed (14)
Duration  2.79s (tests 40%, import 27%, transform 17%, worker 15%)
```

Final production build, including the newly measured report, exit 0:

```text
> npm.cmd run build
> tsc --noEmit && vite build
vite v8.3.4 building client environment for production...
✓ 27 modules transformed.
dist/reports/eval.json                                   74.64 kB
dist/reports/eval-c913e0bbc643443d8be95d2374b05210.png  101.36 kB
✓ built in 684ms
```

The earlier build passed too; it emitted Vite plugin-timing diagnostics under
concurrent pipeline work. The final build copies the source report exactly.

Focused acceptance against the final production build, now exercising the
completed-report table rather than the old blocked report, exit 0:

```text
> .\.venv\Scripts\python.exe -m pytest -q -s tests/test_web.py
Running 9 tests using 1 worker
9 passed (36.6s)
1 passed, 1 warning in 67.45s (0:01:07)
```

Browser execution also printed the existing Node `NO_COLOR`/`FORCE_COLOR`
warning. Successful proof/edit/restore cases use a real isolated local EVM and
synthetic fixture records. They do not establish public Sepolia acceptance.

Actual evaluation command, exit **1**, because the control failed:

```text
> .\.venv\Scripts\python.exe -m ecoproof.detect.evaluate --region delhi --baseline-start 2026-10-03T00:00:00Z --baseline-end 2026-10-05T00:00:00Z --start 2026-10-05T00:00:00Z --end 2026-10-12T00:00:00Z --sigma-km 10 --alpha 0.5 --seed 42
"status": "complete"
"case_count": 18
"plume_negative_control_passed": false
```

The third plume trial injected an arrival at station 6254665 on October 5 at
07:00 UTC, and it was labeled SENSOR_FAULT_DRIFT. Its source at station 6957,
06:00 UTC, remained low-confidence VALID. The protection for arrivals requires
a source labeled VERIFIED_PLUME_EVENT, so it did not apply. One of eight affected
observations across three plume trials was called a fault. This is a heuristic
limitation on these inputs; the failure is retained in the chart and report.
The detector's measured fault-type F1 values are low (see the actual report),
so software test passes must not be described as model-validation success.

Actual live-service smoke:

```text
/ HTTP 200
/api/stations HTTP 200
Catalog stations: 94 With classifications: 11
/api/batches?limit=1 HTTP 200
Latest batch records: 7
/api/events?limit=3 HTTP 200
```

Actual Chrome run (`node .cache/submission-browser.mjs`), exit 0:

```text
"catalog_stations": 94
"classified_stations": 11
"map_tiles_loaded": 2
"default_station": "Chandni Chowk, Delhi - IITM"
"verification_http_status": 503
"verified_on_chain": false
"evaluation_status": "complete"
"mobile_no_overflow": true
"browser_javascript_errors": 0
```

The real Verify page shows the actual saved canonical record and proof, then an
unavailable-chain notice. It does not display a fabricated green verdict or
transaction link. Desktop Monitor/Evaluation screenshots were visually inspected.

Credential/content checks:

```text
Credential leaks in frontend/reports/docs: 0
Production report matches source: True
```

The unchanged spec SHA-256 is
`8307cf224dc66ca6767b0842817fbe4f37ef4d830ab2572c778edb79880f2395`;
the unchanged original Bronze weather SHA-256 is
`89e91f8509e7c9a720e0430b592a57410d1c5733be363274edf79df9457283c3`.

### Remaining work and next step

- Fund the existing public test-wallet address via a Sepolia faucet, then deploy,
  submit one real saved batch and demonstrate original-pass/edit-fail using the
  actual public receipt/explorer link. No funding confirmation has been received;
  the last balance check was zero. Do not substitute local fixture transactions.
- Improve and validate model behavior on separate data before claiming that the
  plume control or detection-quality acceptance is met. Preserve this first real
  evaluation as evidence; do not tune the published cases into a passing claim.
- Publish the repository and record/publish the required narrated video using
  the prepared guide and factual description. Neither external action was done.
- The local application is running for review. No task 11 work was started, and
  the project is not described as satisfying every submission requirement.

## October 23 — detector reliability and portfolio evidence

Status: **supported-flatline correction and paired separate-period evaluation
complete; broader model acceptance and public anchoring still incomplete**.
The user requested a stronger hackathon/portfolio project
and will handle GitHub publishing and video. This work stays within the detector
and evaluation requirements; no stretch application feature or AWS migration was added.

### Built and preserved

- Fixed a contradiction in the flat/zero decision path: varying neighbors could
  establish a stuck-sensor hypothesis and then veto it. A supported five-hour
  flat/zero run now has its own suspected-fault decision after the existing
  weather/baseline/current-neighbor safeguards. Two complete supporting peers
  are required. Regional zero readings and a whole steady neighborhood do not
  establish an individual stuck sensor.
- Added six regression cases covering varying pollution without future samples,
  regional zeros, missing source/peer hours and inadequate independent support.
  Numerical thresholds and other fault/plume rules were not changed.
- Preserved the original report, chart and classifier under
  `reports/history/2026-10-23-initial/`. Fixed the comparison protocol in
  `docs/DETECTOR_REVIEW.md` before scoring a separate temporal block.
- Ingested September 23–October 2 for the independent review: 7,497 PM2.5 records,
  11 locations with observations, 240 weather hours, 21 new immutable snapshots.
  A separate Silver build contains both periods: 15,093 readings, 94 catalog
  locations, 480 weather hours, no rejected rows. App Silver remains its earlier
  snapshot. The exact cached files/hashes are in the review's Bronze manifest.
- Added offline before/after and plotting scripts. The comparison checks matching
  input fingerprints, configurations, coverage and injected locations/values.
  The original classifier is imported only by the offline review script.
- Re-ran the original development cases with the corrected detector. Stuck true
  positives increased from 4/36 to 27/36; zero from 6/36 to 27/36. Whole-window F1
  increased from 0.096386 to 0.509434 and from 0.139535 to 0.504673, respectively.
  Unchanged-background flags stayed at 15. Other fault metrics and the failed
  development plume control remain. This is not independent field accuracy.
- Published that corrected development report to the dashboard, retaining the
  original. Rebuilt frontend assets and captured an actual Chrome walkthrough.
- Recomputed the real app classifications and compared every canonical record
  hash: all 1,546 match existing Gold, so no materialized records/batches needed
  replacement and the running services did not need to be stopped.
- Added a portfolio case study and updated the current demo/submission text with
  factual evidence and limitations. No external publishing or video work occurred.

### Files changed

- `src/ecoproof/detect/classifier.py`, `tests/test_classifier.py`.
- `scripts/review_detector.py`, `scripts/plot_detector_review.py`.
- `README.md`, `docs/CLASSIFIER.md`, `docs/EVALUATION.md`, `docs/DETECTOR_REVIEW.md`,
  `docs/PORTFOLIO.md`, `docs/DEMO.md`, `docs/SUBMISSION.md`, `docs/PROGRESS.md`,
  `reports/README.md`.
- `reports/eval.json`, `reports/eval-1f5ae289101c4dba88e4e01c016e40e9.png`,
  the original archive, paired artifacts under `reports/detector-review/`, and
  updated `reports/demo-*.png` / `reports/demo-browser.json`.
- Ignored local changes: new Bronze pulls, the separate Silver database/build,
  Python caches, frontend build and browser test output. No new environment
  setting or credential was needed; `.env.example` remains accurate.

### Actual checks

The first focused run hit the existing Windows sandbox restriction on
`.pytest_cache/tmp`: 60 passed, five fixture-setup errors. The approved retry
completed successfully:

```text
> .\.venv\Scripts\python.exe -m pytest -q tests/test_classifier.py tests/test_evaluate.py
65 passed in 18.51s

> .\.venv\Scripts\python.exe -m pytest -q
424 passed, 2 warnings in 503.85s (0:08:23)

> npm.cmd run build
vite v8.3.4 building client environment for production...
27 modules transformed.
built in 882ms
```

Full-suite warnings remain the websockets legacy and Starlette HTTPX TestClient
deprecations. No tests were skipped to hide a failed requirement. The offline
review/plot scripts also passed `python -m py_compile`.

Development evaluation, exit **1** because the control still fails:

```text
status: complete
case_count: 18
plume_negative_control_passed: false
unchanged_fault_flags: 15
stuck F1: 0.5094339622641509
zero F1: 0.5046728971962616
```

Actual Chrome walkthrough, exit 0:

```text
catalog_stations: 94
classified_stations: 11
map_tiles_loaded: 12
verification_http_status: 503
verified_on_chain: false
evaluation_status: complete
mobile_no_overflow: true
browser_javascript_errors: 0
```

The updated evaluation screenshot was visually inspected. Current HTTP checks
returned 200 for dashboard, API docs and evaluation JSON. The production report
matches the source byte-for-byte. A scan using the actual configured credentials
found zero matches in code/scripts, docs, reports and frontend output; values
were never printed. The spec and original Bronze hashes remain unchanged.

### Uncertainties and next task

Both separate-period commands completed, each with 30 cases over 1,528 observed
rows per copy at ten stations. Identical input/configuration/intervention checks
passed. Actual outputs:

```text
Independent before: exit 0, plume_negative_control_passed: true
stuck F1: 0.0; zero F1: 0.0; unchanged_fault_flags: 4

Independent after: exit 0, plume_negative_control_passed: true
stuck F1: 0.7142857142857143
zero F1: 0.6666666666666666
unchanged_fault_flags: 4

> .\.venv\Scripts\python.exe scripts/plot_detector_review.py
paired_inputs_and_interventions: true (both periods)
exit 0
```

Stuck true positives increased from 0/60 to 45/60, zero from 0/60 to 40/60.
The unchanged-data flags and all spike/drift/degradation metrics were unchanged.
Both revisions had zero false faults on 14 affected plume observations in the
separate period, five supported sources and seven low-confidence affected rows.
This does not resolve the development failure (1/8), which stays on the dashboard.
Rules and numerical settings were frozen before separate-period scoring and
were not changed afterward. Charts, complete JSON reports and the comparison
are saved; the comparison figure was visually inspected.

The original plume failure is retained, and slow drift/degradation/spike
detection remains weak. Public testnet anchoring is still incomplete. This
detector-improvement task stops for user review as requested. Next, prioritize
the real Sepolia deploy/anchor/
original-pass-edit-fail flow; it needs faucet funding of the existing wallet.
The user owns GitHub publication and the video. No task 11 work was started.

## October 24 — public Sepolia deployment and verification

Status: **public deployment, one real batch anchor, and original-pass/edit-fail
demonstration complete**. The user confirmed the existing wallet was funded.
The live RPC confirmed chain ID 11155111 and a balance of 0.05 Sepolia ETH before
deployment. This task used that existing throwaway wallet and saved real data.

### Built and configured

- Deployed the compiled BatchRegistry at
  `0xb120d4671607E7C24F6C14C4f23B589F5f4484EB`.
  [Deployment transaction](https://sepolia.etherscan.io/tx/0x4a57758efaa4c467b8becb82625e6084a8fc2b054d5ffb01c0945d6d38482b67)
  mined in block 11981959, using 2,112,789 gas.
- Anchored the existing seven-record batch
  `ecoproof:v1:valid:20261011T230000Z:e7aaf8938d201639002bfed699ed30b73674746c28d460ad4f1ce594aa67efc0`.
  [Anchor transaction](https://sepolia.etherscan.io/tx/0xbc325583e39e7778538a69878d9507281444a2e508ce13f048df455096ca5e49)
  mined in block 11981966 at 2026-10-24 06:16:24 UTC, using 239,742 gas.
- Both receipts have status 1. Confirmed registry code/address, anchor event,
  canonical block header, root, count and time bounds against the saved batch.
  Deployment/submission journals retain the signed intent for safe recovery.
- Saved the mined `REGISTRY_ADDRESS` in ignored `.env`. Existing RPC/key settings
  were reused. `.env.example` already documents every required setting.
- Verified ownership before stopping the project's API for the database write,
  then restarted it with the registry configuration. The dashboard is running at
  <http://127.0.0.1:5173>; API docs at <http://127.0.0.1:8000/docs>.
- Checked station 17 (R K Puram), 2026-10-11 23:00 UTC, leaf index 0. Its original
  value 22.0000 verifies against Sepolia; changing it to 23.0000 fails. Chrome
  also restored the original and verified it again. No saved record was edited.
- Saved public receipt/readback evidence, the original canonical payload/proof,
  actual API verdicts and new screenshots. Visually inspected the green original
  and red edited-record screenshots. Updated the current demo/submission/portfolio
  descriptions while retaining the known detector limitations and historical log.

### Files changed

- `README.md`, `docs/ANCHORING.md`, `docs/DEMO.md`, `docs/SUBMISSION.md`,
  `docs/PORTFOLIO.md`, `docs/PROGRESS.md`, `contracts/README.md`, `web/README.md`,
  `reports/README.md`.
- New `reports/sepolia-demo.json`, `reports/sepolia-proof.json`, and
  `reports/demo-tampered.png`; updated `reports/demo-browser.json` and the
  Monitor, Verify, Evaluation and mobile screenshots.
- Ignored local state: `.env`, deployment journal, DuckDB anchor submission and
  batch receipt fields, runtime logs/metadata, browser/evidence helper scripts,
  original/edited verification inputs, and test/build caches.
- No application/classifier/contract source change was needed. No new environment
  variable was introduced. `docs/SPEC.md` remains unchanged.

### Actual tests and checks

```text
> npm.cmd run compile  (inside contracts/)
No contracts to compile

> .\.venv\Scripts\python.exe -m pytest -q
424 passed, 2 warnings in 342.61s (0:05:42)

CLI read: exit 0
root: e7aaf8938d201639002bfed699ed30b73674746c28d460ad4f1ce594aa67efc0
record_count: 7

CLI original verify: exit 0
verified: true
CLI edited verify: exit 1 (expected rejection)
verified: false

> node .cache/submission-browser.mjs
verification_http_status: 200
verified_on_chain: true
tampering_rejected: true
restored_record_verified: true
catalog_stations: 94
classified_stations: 11
map_tiles_loaded: 12
mobile_no_overflow: true
browser_javascript_errors: 0
exit 0
```

The full suite ran with approved access because its Windows scratch directories
and local EVM/browser fixtures have required it. The two warnings are the existing
websockets legacy and Starlette HTTPX TestClient deprecations. Software tests and
this separate public verification are both recorded; local fixtures did not
substitute for a public transaction.

The actual browser POST responses were HTTP 200 with codes `verified`,
`record_mismatch`, and `verified`. The link in the UI matches the real anchor
transaction. Dashboard and `/stations` HTTP checks returned 200 after restart.
A scan of 139 public files/frontend build files found zero files containing the
configured credentials. Git ignores the environment, deployment journal and
local edited input. The spec hash and the previously recorded original weather
Bronze hash both remain unchanged. Bronze/Silver/Gold were not rebuilt.

### Uncertainties and next task

Exactly one of 165 prepared batches is anchored; 164 still display saved-only
status. Verification reads the configured Sepolia RPC and registry, and proves
the canonical record's integrity rather than sensor accuracy. Public receipts
establish mined inclusion; they are not a promise of irreversible finality.

The development plume control still fails (one false fault among eight affected
observations), and spike/drift/degradation detection remains weak. Those findings
were not altered by this provenance task. The next engineering task for review is
the unresolved plume handling and separate-data validation, within the deadline.
The user manages GitHub publication and the narrated video. No AWS integration or
task 11 work was added. Stop here for the user's review.

## October 24 — plume ambiguity correction and separate-period validation

Status: **known development false fault resolved; all three measured plume
controls pass**. This task adds a narrow uncertainty safeguard and preserves
the weak spike/drift/degradation results. No numerical threshold was tuned.

### Built and preserved

- Diagnosed `plume-18`: a source anomaly at 6957, October 5 06:00 UTC, was
  followed by a receiver rebound at 6254665 one hour later. Falling background
  pollution left the receiver below its older six-hour rise reference, preventing
  strict plume confirmation; the receiver was then called an isolated fault.
- Added `possible_upwind_transport` for an otherwise isolated positive anomaly.
  It requires an observed positive receiver step, a recent anomalous/rising
  source, source-time wind alignment and consistent travel time inside the graph.
  Suspected-fault sources cannot clear other faults; newly uncertain arrivals
  cannot recursively become sources. Flat/zero and persistent-drift decisions
  are outside this fallback. The receiver stays low-confidence VALID, with
  source links; this is not a new confirmed-plume claim.
- Added ten synthetic regression cases. Two reproduced the original bug before
  the fix; the others protect calm/upwind/impossible transport, absent/weak/fault
  sources, missing receiver data, non-rising and negative anomalies.
- Archived the previous classifier, report and chart under
  `reports/history/2026-10-24-pre-plume/`. Pinned both versions of the earlier
  flatline review so later code changes cannot silently alter that comparison.
- Fixed the new protocol in `docs/PLUME_REVIEW.md` before scoring the new period.
  The corrected classifier SHA-256 is
  `b4dbcd390245fb3147217e8237c0633a2407c484a648b37bd76a804d2eaf0982`.
  It was not changed after scoring. The previous hash was
  `450ed3dcc326c89d4d9b6406c374d3ab433fc8ffa7dd2c47d6ea978b8e809af1`.
- Ingested October 13–22: 8,065 PM2.5 rows from 12 locations, 240 weather hours,
  20 new immutable snapshots. The separate Silver build contains all three
  periods: 23,158 readings, 94 catalog stations and 720 weather hours, zero
  rejected rows. The 85-source manifest records exact names/hashes.
- Added offline paired evaluation/plot scripts. They verify frozen source hashes
  and compare fingerprints, settings, station coverage and every intervention.
  Earlier development/regression before measurements were reused only after
  matching those sources/inputs; the new before/after period was executed.
- Added memoization of pure wind-weight matrices in the offline driver only.
  Three distinct synthetic cases and reversed reuse match uncached full
  classifications exactly. The first unoptimized development/regression runs
  were interrupted and restarted with this computation reuse before any result
  was published. No thresholds, inputs or intervention plans changed.
- The original unbounded Silver build was slow but completed successfully before
  an attempted interruption. SQL batching was investigated against DuckDB 1.5
  documentation and a constrained in-memory example; no transform source change
  was applied or needed to finish this task.
- Published the corrected development report/chart to the dashboard, updated
  submission/portfolio descriptions and captured fresh real-workspace Chrome
  screenshots. Inspected the evaluation screenshot and paired comparison figure.
- Recomputed the current app classifications: all 1,546 canonical hashes match
  existing Gold, including all seven publicly anchored records. The live database,
  deployment and saved proofs needed no rebuild or additional chain transaction.

### Files changed

- `src/ecoproof/detect/classifier.py`, new `tests/test_plume_ambiguity.py`.
- New `scripts/review_plume.py`, `scripts/plot_plume_review.py`; pinned archived
  sources in `scripts/review_detector.py`.
- `README.md`, new `docs/PLUME_REVIEW.md`, `docs/CLASSIFIER.md`,
  `docs/EVALUATION.md`, `docs/DETECTOR_REVIEW.md`, `docs/DEMO.md`,
  `docs/SUBMISSION.md`, `docs/PORTFOLIO.md`, `docs/PROGRESS.md`,
  `reports/README.md`, `web/README.md`.
- `reports/eval.json`, its new `eval-2e4e70c91161426d9510479f6ebc7bea.png`,
  the pre-plume archive, all artifacts under `reports/plume-review/`, and
  updated `reports/demo-*.png` / `reports/demo-browser.json`.
- Ignored local state: new Bronze pulls, the separate Silver database/build,
  snapshot-check helper, test caches and frontend build. No environment variable
  or credential was added; `.env.example` remains accurate. `docs/SPEC.md` is unchanged.

### Actual tests and results

The initial regression run intentionally exposed the two missing behaviors:

```text
> .\.venv\Scripts\python.exe -m pytest -q tests/test_plume_ambiguity.py
2 failed, 8 passed, 2 warnings in 0.89s
```

Those warnings were Windows sandbox denial of pytest cache writes. After the
fix, the approved focused and full runs passed:

```text
> .\.venv\Scripts\python.exe -m pytest -q tests/test_classifier.py tests/test_plume_ambiguity.py tests/test_evaluate.py
75 passed in 31.99s

> .\.venv\Scripts\python.exe -m pytest -q
434 passed, 2 warnings in 449.94s (0:07:29)

> npm.cmd run build  (inside web/)
vite v8.3.4 building client environment for production...
27 modules transformed.
built in 10.69s
```

The full-suite warnings are the existing websockets legacy and Starlette HTTPX
TestClient deprecations. Vite also printed callback timing information. The three
review scripts passed `py_compile`; the plot command exited 0 with all pairing
checks true. No tests were skipped to hide a failed requirement.

Actual experiment summaries (all fault metrics stayed unchanged):

```text
Development before: exit 1; plume false faults 1/8; low confidence 6/8
Development after:  exit 0; plume false faults 0/8; low confidence 7/8
Regression before/after: exit 0; plume false faults 0/14; low confidence 7/14
New validation before/after: exit 0; plume false faults 0/15; low confidence 6/15
Unchanged-data fault flags, before/after: 15/15, 4/4, 16/16
```

The new period scores 1,787 rows per copy at 12 locations, with 11 represented on
all seven dates. Its input fingerprint is
`b163a9f87a5ed1870f719f1d70e536611cf3921a89749e0ac74bf6d620af06e2`.
New-period F1 before/after: stuck 0.511111, zero 0.494118, spike 0.024096, drift
0.000000, degradation 0.028777. Full precision/recall/confusion counts, source
labels and confidence counts remain in the reports and comparison JSON.

Actual Chrome walkthrough, exit 0:

```text
verification_http_status: 200
verified_on_chain: true
tampering_rejected: true
restored_record_verified: true
catalog_stations: 94
classified_stations: 11
map_tiles_loaded: 12
evaluation_status: complete
mobile_no_overflow: true
browser_javascript_errors: 0
```

Dashboard and API docs returned HTTP 200. The live and production evaluation JSON
match the published report. All 85 Bronze files match their manifest and the spec
hash is unchanged. A scan of 163 public/build files found zero configured-credential
matches; credentials were not printed or committed.

### Uncertainties and next task

The known development false fault is resolved by uncertainty handling, not by
claiming additional confirmed plume sources. The separate periods show no
regression in these selected cases, not established field accuracy. Spike,
gradual drift and degradation still score poorly; broader model research and
independently labeled validation exceed a safe last-day scope expansion.

The core prototype, measured evaluation and public proof flow are demonstrated.
Next task for review: final submission-readiness and handoff check, with the
documented limitations retained. The user owns public GitHub publication and
the narrated video. No AWS integration or stretch task 11 was started. Stop here
for the user's review.

## October 24 — Final submission handoff

### What was built and checked

- Prepared `docs/HANDOFF.md`: checklist against spec section 13, clear
  fresh-checkout instructions, an owner publication checklist and a timed
  4 minute 30 second video script using actual saved examples.
- Added a read-only public-demo proof checker. It pins the published Sepolia
  contract/batch, reads the root and count from the chain, checks metadata and
  canonical payload consistency, and verifies the saved sibling path without
  opening DuckDB or using a private key. `--tamper` edits the value in memory;
  original/edit/restore returned true/false/true with exit codes 0/1/0.
- Exported the nonignored source into a separate checkout directory, without
  `.env`, a database or dependency directories. Installed its own locked Python
  and npm dependencies and confirmed imports came from that exported source.
  This was a fresh source export, not a public Git clone: this repository has
  no initial commit, refs or remote.
- Found and fixed a real first-run test issue: pytest creates its configured
  temporary directory without creating its parent. A test-session hook now
  creates that parent. Checked the installed pytest `getbasetemp` implementation
  and session-start hook documentation before the fix.
- Corrected stale API/weather-only and unfunded-wallet notes. Rehearsed the
  populated real dashboard in Chrome, including public verification, tampering,
  restore, map/charts, evaluation and mobile layout.

### Files changed

- New `scripts/verify_public_demo.py`, `tests/test_public_demo.py` and
  `docs/HANDOFF.md`; updated `tests/conftest.py`.
- `docs/PORTFOLIO.md` now includes the final test count and portable proof check.
- `README.md`, `data/README.md`, `docs/API.md`, `docs/ANCHORING.md`,
  `docs/DEMO.md`, `docs/SUBMISSION.md`, `docs/PROGRESS.md`, `reports/README.md`.
- New `reports/handoff-check.json`; refreshed `reports/demo-browser.json` and
  the five `reports/demo-*.png` screenshots.
- Ignored local source export, fresh environments, validation helpers/logs and
  build/test caches. No new environment setting was needed; `.env.example`
  remains accurate. No ingestion, database rebuild, signing or public transaction
  was performed in this task. `docs/SPEC.md` was not changed.

### Actual tests and results

Before adding the proof-checker tests, the full existing workspace suite passed:

```text
> .\.venv\Scripts\python.exe -m pytest -q
434 passed, 2 warnings in 665.87s (0:11:05)

> .\.venv\Scripts\python.exe -m pytest -q tests/test_public_demo.py --basetemp=.cache/public-demo-tests -p no:cacheprovider
13 passed, 1 warning in 5.62s
```

The first browser/proof test attempt in the fresh export exposed the missing
temporary-directory parent; this was a failure, not a passing clean-start test:

```text
> .\.venv\Scripts\python.exe -m pytest -q tests/test_public_demo.py tests/test_web.py
FileNotFoundError: [WinError 3] ... .pytest_cache/tmp
13 passed, 1 warning, 1 error in 55.63s
```

After fixing the session setup, the full suite passed in the clean export using
a previously absent temporary-directory parent (`Test-Path` returned `False`
before starting):

```text
> .\.venv\Scripts\python.exe -m pytest -q --basetemp=.cache/first-run-test-parent/tmp
447 passed, 3 warnings in 10342.69s (2:52:22)
```

This includes the 13 new proof checks and the existing local-EVM/browser
acceptance wrapper. The real elapsed output above is retained verbatim. Warnings
were the existing websockets/Starlette deprecations and a Windows access denial
when writing pytest's optional node-ID cache. Test temporary directories and
all assertions succeeded. No tests were skipped to obtain this result.

Fresh dependency/build execution:

```text
> uv sync --locked
Resolved 73 packages in 5ms
Installed 71 packages in 7.75s

> npm.cmd --prefix contracts ci --offline --no-audit --no-fund
added 61 packages in 1m

> npm.cmd --prefix contracts run compile
Compiled 1 Solidity file with solc 0.8.20 (evm target: shanghai)

> npm.cmd --prefix web ci --offline --no-audit --no-fund
added 51 packages in 42s

> npm.cmd --prefix web test
Test Files  2 passed (2)
Tests  14 passed (14)
Duration  2.76s

> npm.cmd --prefix web run build
27 modules transformed.
built in 1.29s
```

The initial sandboxed uv command could not read the Windows cache. An approved
offline attempt then found numpy missing from cache; the approved normal locked
install downloaded the missing numpy/matplotlib wheels and completed. Those
setup failures were not reported as successful offline installation.

The public proof check in the export had no `.env` or database and received only
the RPC credential. Both before and after checks confirmed no database existed.
Actual output is retained in `reports/handoff-check.json`:

```text
original: exit 0, verified true
edited:   exit 1, verified false
restored: exit 0, verified true
api_docs_http_status: 200
frontend_http_status: 200
empty_data_http_status: 503
empty_data_detail: Data database is missing; ingest observations and build Silver/Gold first
published_evaluation_and_chart_match: true
owned_test_services_stopped: true
```

The fresh-checkout API/frontend checks used separate ports and stopped only their
owned temporary processes. The original populated dashboard remains running.
Its actual Chrome rehearsal exited 0 with:

```text
verification_http_status: 200
verified_on_chain: true
tampering_rejected: true
restored_record_verified: true
catalog_stations: 94
classified_stations: 11
map_tiles_loaded: 12
evaluation_status: complete
mobile_no_overflow: true
browser_javascript_errors: 0
```

All 85 Bronze files still match their manifest, and the spec SHA-256 remains
`8307cf224dc66ca6767b0842817fbe4f37ef4d830ab2572c778edb79880f2395`.
The local-document audit checked 99 links with zero missing file targets.
Prepared the local `.cache/EcoProof-submission.zip` archive from 162 nonignored
source files, plus an embedded checksum list. Every archive entry was read back
and checked. The scan found zero matches for configured OpenAQ, RPC or private-key
values; no `.env` or database was included. The final archive hash and file
manifest are in ignored `.cache/EcoProof-submission-manifest.json`. The original
dashboard and API docs both returned HTTP 200 again at 18:12 UTC.

### Uncertainties and next task

Full real-data ingestion was not repeated in the clean export; its empty-data
behavior, dependency installation, saved evaluation and public-proof path were
checked. Fresh provider pulls can change inputs and cannot reconstruct private
transaction journals. The original real-data run and its exact commands remain
documented. The proof depends on the selected RPC's chain response and proves
record integrity, not sensor or model accuracy. Weak fault-type scores and
plume uncertainty remain explicit.

The owner still needs to publish GitHub, record/upload the 3–5 minute video,
confirm eligibility and complete the hackathon submission before October 25,
19:00 GMT+5. No public repository, video, hosting service or final submission
was created here. No AWS work or stretch task 11 was started.

This handoff task is complete. Next action: owner publication, video and
submission using `docs/HANDOFF.md`. Stop here for the user's review.

## October 25 — Save the full video script

- Built: saved the complete narration, seven timed recording sections, exact
  demo links, example events, original/edit/restore actions, and recording/upload
  checklist in `docs/VIDEO_SCRIPT.md`. Linked it from the handoff guide.
- Files changed: `docs/VIDEO_SCRIPT.md`, `docs/HANDOFF.md`, `docs/PROGRESS.md`.
- Checks: read the saved UTF-8 file and checked its sections, required script
  content and relative links. The first check's curly apostrophe was replaced
  during PowerShell-to-Python input encoding; rerunning with an ASCII check
  string passed without changing the document. Actual final output:

```text
VIDEO_SCRIPT.md: 7 timed sections; 5 local links valid; narration and recording instructions present.
HANDOFF.md: video-script link present and target exists.
```

- Application tests were not repeated for this documentation-only save. The
  script's 447-test statement refers to the previously recorded full run, not
  a new execution. No application code, data, credentials or spec was changed.
- Uncertainties: recording duration depends on speaking pace; the suggested
  timings need rehearsal. Replace the name placeholder and add the real GitHub
  URL after publication.
- Next task: user reviews the script, rehearses and records the demo. Stop here
  for review.

## October 25 — GitHub publication and portfolio README

### What was prepared

- Reworked the README around the actual product: a real dashboard screenshot,
  public original/edit/restore proof, implementation decisions with source links,
  Mermaid architecture, measured evaluation, practical setup and clear limits.
  The longer operational reference is preserved in `docs/DEVELOPMENT.md`.
- Added the supplied public repository URL to the submission, handoff, demo,
  portfolio and video guides. No hiring outcome, model accuracy, CI result or
  hosted dashboard was invented.
- Prepared the initial publication of the project's source, tests, lockfiles,
  documentation, public reports and MIT license to
  `https://github.com/ks-exe/EcoProof_Climate-Data-Environmental-Monitoring`,
  branch `main`, as explicitly requested by the owner.
- GitHub returned HTTP 200 for the public repository. Its advertised refs were
  empty before publication; the local repository also had no initial commit.
  Existing Git author identity is configured. No existing remote work needs
  replacement or a force push.

### Files changed and publication boundary

- `README.md`, new `docs/DEVELOPMENT.md`, `docs/SUBMISSION.md`,
  `docs/HANDOFF.md`, `docs/DEMO.md`, `docs/PORTFOLIO.md`,
  `docs/VIDEO_SCRIPT.md`, `docs/PROGRESS.md`.
- The first commit will also contain the existing project implementation,
  tests and public evidence, which were previously untracked locally.
- The pre-stage audit inspected 164 nonignored files and 137 local document
  links: zero configured-credential matches and zero missing link targets.
  Git ignore checks confirmed `.env`, the database, deployment journal,
  dependencies and `.cache` are excluded.
- `docs/SPEC.md` and the current/archived classifier source hashes are unchanged.
  Their LF bytes match their recorded hashes and will not change during Git's
  line-ending normalization. Application code and real data were not modified.

### Actual release checks

```text
> .\.venv\Scripts\python.exe -m pytest -q
447 passed, 2 warnings in 367.12s (0:06:07)

> npm.cmd --prefix web test
Test Files  2 passed (2)
Tests  14 passed (14)
Duration  4.94s

> npm.cmd --prefix web run build
27 modules transformed.
built in 8.60s
```

The Python warnings are the existing websockets legacy and Starlette HTTPX
TestClient deprecations. Vite printed callback timing information; the build
exited 0. The full suite includes the isolated local EVM and browser acceptance.
The first sandboxed Git remote inspection failed with a Windows Schannel
credential error; the approved inspection outside the sandbox succeeded.

### Publication and next action

Published the initial source commit
`7ef7e619f242fcbf92105c43321b1a3732fd91ab` to `origin/main`. Actual Git output:

```text
branch 'main' set up to track 'origin/main'.
To https://github.com/ks-exe/EcoProof_Climate-Data-Environmental-Monitoring.git
 * [new branch]      main -> main
```

The first metadata write was blocked because Git's repository directory belongs
to the sandbox account. Publishing used an explicit `safe.directory` option
limited to this project on each command; no global trust exception was added.
The staged Git blobs were scanned before committing: 164 files, zero configured
credential matches, preserved spec/classifier bytes and a clean `git diff
--cached --check`.

Post-push checks against GitHub returned:

```text
remote_commit_matches_local: true
repository_http_status: 200
readme_matches_committed_bytes: true
readme_visible_on_repository_page: true
dashboard_and_evaluation_images: HTTP 200, match local bytes
published_files: 164
private_local_files_excluded: true
```

The repository is public. No force push or replacement of existing remote
history was needed. This follow-up progress entry records the already verified
publication; the application and README are unchanged from the tested source
commit. The video URL is still pending. Next: owner reviews the repository,
records/uploads the video and submits before the deadline. Stop for review.
