# EcoProof development reference

Detailed setup, pipeline commands, storage contracts and implementation notes.
For the project overview and public proof, see the [README](../README.md).

## Setup

Use Python **3.11** for development, as specified in AGENTS.md. Package metadata
allows Python 3.11+ per spec section 2. Install [uv](https://docs.astral.sh/uv/),
then run from this repository root:

```text
uv sync --locked
```

uv installs Python 3.11 if needed. On Windows, the development dependencies
include GNU Make 4.4.1 from the [gnumake distribution](https://pypi.org/project/gnumake/).
On macOS/Linux, install GNU Make using your system package manager if it is missing.

Solidity and browser integration tests also need **Node 22.13+**, the locked tools
in `contracts/` and `web/`, and Chrome. Install and check them before the full Python suite:

```text
cd contracts
npm ci
npm test
npm run compile
cd ../web
npm ci
npm test
npm run build
cd ..
```

In PowerShell use `npm.cmd` if execution policy blocks `npm.ps1`. The compiler is
locked as an npm dependency. Python tests compile the registry and start/stop a
temporary localhost EVM; missing tooling causes a test failure, not a skipped check.
The browser acceptance test also starts/stops its own local API and built frontend,
using a separate synthetic dataset. See [frontend tests and browser choices](../web/README.md).

Create the local environment file only if it does not already exist:

```powershell
# Windows PowerShell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

```sh
# macOS / Linux
test -f .env || cp .env.example .env
```

Set `OPENAQ_API_KEY` in `.env` for OpenAQ ingestion. Obtain a free key from
<https://explore.openaq.org/register>. Open-Meteo and offline tests need no key.
`.env` and local data are ignored by Git.
`OPENAQ_API_KEY`, `RPC_URL`, and `PRIVATE_KEY` are backend-only settings. Use a
funded throwaway Sepolia wallet for task 8 deployment/submission. The CLI enforces
chain ID 11155111. `REGISTRY_ADDRESS` can specify an existing registry; otherwise
the client uses its mined deployment journal. See [anchoring setup](../docs/ANCHORING.md).

Run the tests in the project's environment:

```text
uv run --locked make test
uv run --locked pytest -q
```

With the virtual environment activated, `make test` runs the same tests.
In PowerShell, activate it with `.\.venv\Scripts\Activate.ps1`; on macOS/Linux,
use `source .venv/bin/activate`.
If GNU Make is not installed, `uv run --locked pytest -q` runs the test suite
directly. Do not install the unrelated PyPI package named `make`.

pytest keeps its disposable test directories in `.pytest_cache/tmp` inside the
repository and recreates that directory on each run. The test session creates
the parent directory when it is absent on a fresh checkout. This avoids permission
conflicts with shared Windows temporary folders.

## Configuration

`ecoproof.config.load_settings()` reads the repository-root `.env`, then applies
process environment overrides. Empty credentials are represented as `None`;
no credential is required to run the offline tests. Values are literal: `${...}`
interpolation is disabled. Settings hide credentials (including RPC URLs) from
their representation and do not mutate the process environment.

`ECOPROOF_DATA_DIR` defaults to `data/`. Relative paths resolve against the
repository root, regardless of the current working directory. Loading settings
does not create directories, a database, or network connections. `make build`
creates the DuckDB database and Silver Parquet files from local Bronze data.

## Layout and intended architecture

```text
OpenAQ + Open-Meteo
    -> immutable Bronze JSON
    -> validated Silver Parquet + DuckDB views
    -> station graph + wind-aware classifier
    -> Gold records + measured injection evaluation
    -> Merkle proofs + testnet BatchRegistry
    -> FastAPI -> React / Vite / Leaflet
```

The components above run on real observations locally, with one publicly
anchored batch. Broader detector validation is needed before operational use.
`src/ecoproof/` contains the section 3 module paths. `data/bronze` holds local raw
pulls; `data/silver` and `data/gold` hold saved builds. `reports/`
holds generated evaluation reports and charts, including explicit blocked status
when observations are unavailable. `contracts/` contains the tested registry,
Hardhat setup, and deployment wrapper. `web/` contains the React/Vite/Leaflet
frontend and its unit and browser checks.

## Commands

| Command | Current behavior |
| --- | --- |
| `make test` | Runs `python -m pytest -q`. |
| `make ingest ARGS="..."` | Pulls or reuses OpenAQ/Open-Meteo Bronze responses. |
| `make build ARGS="--region ..."` | Rebuilds Silver Parquet and the three `silver.*` DuckDB views from Bronze. |
| `make detect ARGS="..."` | Classifies Silver into Gold using explicit baseline/output windows; `--rebuild-silver` rebuilds from Bronze first. |
| `make eval ARGS="..."` | Evaluates independent injection copies of Silver and saves a report/chart; missing data produces blocked status and a nonzero exit. |
| `make anchor ARGS="..."` | Prepares hourly batches, deploys/resumes a registry, submits one batch, reads roots, or verifies a record on Sepolia. Missing prerequisites produce a nonzero exit. |
| `make api` | Starts the read-only FastAPI service at localhost:8000; `/docs` describes the six MVP endpoints. |
| `make web` | Starts React/Vite/Leaflet at localhost:5173, proxying the local API. |

The Makefile allows `PYTHON` to be overridden if needed. Current demo instructions
and the exact real-data run are in [docs/DEMO.md](../docs/DEMO.md).

## Ingest data

Repeat the verified weather pull (the same request reuses its local cache):

```text
uv run --locked make ingest "ARGS=--source openmeteo --region delhi --latitude 28.6139 --longitude 77.2090 --start-date 2026-10-05 --end-date 2026-10-11"
```

After setting the OpenAQ key, first inspect the station catalog. The October 23
Delhi check returned 94 catalog locations; actual time coverage must also be checked:

```text
uv run --locked make ingest "ARGS=--source locations --region delhi --latitude 28.6139 --longitude 77.2090 --radius-m 25000"
```

Then fetch PM2.5 measurements for up to ten nearby stations plus regional weather:

```text
uv run --locked make ingest "ARGS=--source all --region delhi --latitude 28.6139 --longitude 77.2090 --radius-m 25000 --start-date 2026-10-05 --end-date 2026-10-11 --station-limit 10"
```

The October 23 run used 12 candidate locations and October 3–12 inputs, including
calibration and later context; see docs/DEMO.md for the exact commands. Catalog
lifetime ranges only identify candidates: inspect actual per-station coverage.
Ten stations have observations across the requested week; two candidates are sparse.

Use `--source openaq` for air data alone, `--refresh` to append new snapshots, or
`uv run --locked python -m ecoproof.ingest --help` for all options. Date arguments
refer to UTC dates. Read [ingestion notes](../docs/INGESTION.md) for API references,
cache format, retries, and timing conventions.

## Build and query Silver

Rebuild from local Bronze with one command; no network or API key is needed:

```text
uv run --locked make build "ARGS=--region delhi --start-date 2026-10-05 --end-date 2026-10-11"
```

The command writes typed `stations.parquet`, `readings.parquet`, `weather.parquet`,
and `build_report.json` into a new directory under `data/silver/`. A DuckDB
transaction switches `silver.stations`, `silver.readings`, and `silver.weather`
to that completed build. Earlier files remain available. Query these views;
reading every Parquet file recursively would combine old and current builds.

For example, save or run this Python snippet in the project environment:

```python
import duckdb
from ecoproof.config import load_settings

with duckdb.connect(str(load_settings().duckdb_path), read_only=True) as db:
    print(db.execute("SELECT count(*) FROM silver.weather").fetchone())
    print(db.execute("SELECT count(*) FROM silver.readings").fetchone())
```

The current demo Silver snapshot includes 7,596 readings and 240 weather hours
from the October 3–12 requests, including provider interval-ending boundary
records. The flatline review's separate two-period build contains 15,093 readings
and 480 weather hours. The plume review additionally cached October 13–22 observations. Its isolated
build and input manifest are documented in [the review](../docs/PLUME_REVIEW.md);
subsequent unbounded rebuilds also include that third period. Inspect
`station_coverage`, rejections, duplicates and warnings after
every rebuild. Seven distinct dates alone do not establish complete sampling.

Invalid rows are excluded with their reason and Bronze file/index in the report.
Malformed source files stop the build. PM2.5 must be finite and within 0–1500
µg/m³. Duplicate keys keep the latest valid row by pull timestamp, filename, and
row order. All stored `TIMESTAMP` values mean UTC. See
[Silver rules and storage details](../docs/SILVER.md) for the full contract.

## Station graph and wind weights

`ecoproof.graph.geo` implements spec section 5, steps 1–2, using Python's standard
library. Pass coordinates as `(latitude, longitude)` in degrees. Output is a list
of rows, in the same station order as the input; entry `[i][j]` means **i to j**.
Keep station IDs alongside that order when reading from `silver.stations`.

```python
from ecoproof.graph.geo import adjacency_matrix, haversine_km, wind_vector, wind_weights

# Synthetic coordinates for this example, not ingested station observations.
coordinates = [(0.0, 0.0), (-0.05, 0.0)]
distance_km = haversine_km(*coordinates)
base = adjacency_matrix(coordinates, sigma_km=10.0)  # tau_km defaults to 20
travel = wind_vector(speed_m_s=5.0, direction_from_deg=0.0)  # east, north: southward
weighted = wind_weights(
    coordinates, sigma_km=10.0, tau_km=20.0,
    speed_m_s=5.0, direction_from_deg=0.0, alpha=0.5,
)
assert abs(weighted[0][1] / base[0][1] - 1.5) < 1e-12
assert weighted[1][0] == base[1][0]
```

Base weights are `exp(-d² / (2 * sigma_km²))` for distinct nodes at distance
`d <= tau_km`, otherwise zero. Haversine uses a spherical mean Earth radius of
6,371.0088 km. It handles longitude wrap and clamps rounding at antipodes.
Sigma must be positive, tau nonnegative, and coordinates finite and in range.

Wind directions say where wind **comes from**: 0/360° north, 90° east, 180° south,
270° west. Travel components are `(-speed * sin(dir), -speed * cos(dir))` in the
east/north axes. Speeds use **m/s**, matching Silver weather. The cosine uses the
initial great-circle direction from i to j in i's local east/north plane. The
multiplier is `1 + alpha * max(0, cosine) * min(speed / 5, 2)`, so downwind edges
receive a boost, crosswind/upwind edges retain their base weight, and the speed
factor saturates at 10 m/s. The matrix generally becomes asymmetric and is not
row-normalized.

**Sigma and alpha are required arguments; example values are not tuned values.**
Alpha must be finite and nonnegative. Calm wind or alpha zero preserves the base
matrix; invalid/missing wind raises `ValueError`. Distinct colocated nodes retain
base weight 1 without a directional boost; self-edges stay zero. An undefined
antipodal bearing also receives no boost. Empty and single-node inputs are valid.
Each call calculates weights for one regional wind observation. The classifier
uses these matrices with the available readings at each hour.

## Classify hourly readings

Choose an earlier, presumed-healthy baseline and a later output window. Times
must include a timezone and fall on UTC hours; end bounds are exclusive. Sigma
and alpha are explicit, untuned inputs. For example, after ingesting suitable air
data, this command rebuilds Silver and Gold from local Bronze without API calls:

```text
uv run --locked make detect "ARGS=--rebuild-silver --region delhi --baseline-start 2026-10-05T00:00:00Z --baseline-end 2026-10-06T00:00:00Z --start 2026-10-06T00:00:00Z --end 2026-10-12T00:00:00Z --sigma-km 10 --alpha 0.5"
```

Omit `--rebuild-silver` to use the current Silver views. The example requests six
output days after a one-day baseline; a full seven-day classification needs a
longer input period, plus three hours of later readings for plume decisions.
The actual demo uses October 3–4 for calibration and October 5–11 for output.
The original one-day baseline provided only 15–23 usable hours per station;
the additional earlier day satisfies calibration without lowering its minimum.

The command averages samples into UTC hours ending at each output timestamp,
uses matching hourly weather, and never fills missing readings. It fits each
station's residual scale as `max(scale_floor, 1.4826 * MAD)` from the earlier
baseline. Defaults are a 1 µg/m³ scale floor, 24 usable baseline hours, and the
spec's 2.5 z threshold. These are initial settings requiring evaluation.

Suspected faults require neighbor evidence. A delayed downwind rise can support
`VERIFIED_PLUME_EVENT`; a receiving station linked to that source is protected
from being labeled an isolated fault. Missing weather, insufficient neighbors or
baseline, incomplete follow-up, and conflicting evidence retain `VALID` with a
low-confidence flag. **`VALID` with low confidence does not mean verified healthy.**
Labels use up to three hours of later readings, so this is retrospective analysis.
Supported five-hour flat/zero runs use two complete neighboring series and do
not need future samples or stable neighboring pollution. They remain suspected
faults, with explicit safeguards against labeling a regional zero run as an
individual sensor failure.

A positive spike can also remain uncertain when a recent upwind anomaly and an
observed rise fit the transport window, even if the strict plume rule cannot
confirm it against the older local reference. The `possible_upwind_transport`
reason preserves that distinction. This fallback never upgrades a row to a
confirmed plume or overrides a flatline/persistent-drift reason.

Each build writes `classified.parquet`, `classification_evidence.parquet`, and
`build_report.json` under `data/gold/build-.../`. The `gold.classified` view keeps
the spec's columns. Each record gets a canonical `record_hash`; `batch_id` is
resolved in the view only when a saved batch snapshot matches that hash.
Confidence, reason, scale, smoothing, and plume/source evidence are in the
companion `gold.classification_evidence` view. Consumers must join them:

```sql
SELECT c.station_id, c.ts, c.value, c.expected, c.z, c.label,
       e.low_confidence, e.reason
FROM gold.classified c
JOIN gold.classification_evidence e USING (station_id, ts)
ORDER BY c.station_id, c.ts;
```

See [classifier rules, choices, and schema proposal](../docs/CLASSIFIER.md).
The spec requires low-confidence handling but omits its storage fields; that
document proposes adding `low_confidence` and `reason` to `gold.classified`.
`docs/SPEC.md` remains unchanged.

## Evaluate injected faults

Use a presumed-clean week with at least eight stations, an earlier baseline, and
later plume context. The evaluator reads Silver without changing Bronze, Silver,
or Gold. The executed run uses **October 3–12** input, with October 3–4 calibration,
October 5–11 output and later context. After rebuilding those inputs, run:

```text
uv run --locked make eval "ARGS=--region delhi --baseline-start 2026-10-03T00:00:00Z --baseline-end 2026-10-05T00:00:00Z --start 2026-10-05T00:00:00Z --end 2026-10-12T00:00:00Z --sigma-km 10 --alpha 0.5 --seed 42"
```

These graph parameters are untuned. The original 18-case experiment returned
exit 1 for a failed plume control; its report is archived. The current correction
passes the same control (0/8 false faults) while leaving seven affected rows low
confidence. The [paired review](../docs/PLUME_REVIEW.md) retains all fault scores and
the separate-period checks. This is not established field accuracy.

Each stuck, zero, spike, additive drift, multiplicative degradation, and lagged
plume case uses a separate copy. Defaults select three cases per type by seeded
availability/geometry checks, with a `PM2.5 > 150` comparison. Metrics count every
observed output row in each copy, including low-confidence misses and presumed
healthy background. The source data has no real fault labels; precision/recall/F1
describe the injection experiment, not established field accuracy.

[reports/eval.json](../reports/eval.json) records parameters, input fingerprint,
interventions, confusion counts, precision/recall/F1 per fault type, coverage,
and the plume negative control. Its `chart` field names the generated Matplotlib
PNG alongside it, suitable for review and export. A blocked report has `metrics:
null`; its chart says **EVALUATION NOT RUN** and contains no result bars. A later
blocked attempt preserves an existing completed report in favor of
`eval.attempt.json`. See [evaluation methodology](../docs/EVALUATION.md).

## Canonical hashing and Merkle proofs

`ecoproof.provenance.merkle` now provides `canonical_record`, `hash_record`,
`MerkleTree`, `MerkleProof`, and `verify_proof`. The committed payload includes
the Gold data columns plus confidence/reason from the evidence view, excluding
derived `record_hash` and `batch_id`. JSON uses sorted keys, UTF-8, UTC timestamps,
and numeric fields rounded half to even at four decimal places.

Trees sort by `(station_id, ts)`, prefix leaves with `0x00` and parents with
`0x01`, and duplicate the last node at every odd level. Single-leaf proofs work;
empty trees and duplicate keys are rejected. Verification requires a trusted
root and record count. It protects the canonical four-decimal payload; changes
that round to the same value intentionally share a hash.

See [the byte format, proof rules, and runnable synthetic example](../docs/MERKLE.md).
Run the dedicated tests with `python -m pytest -q tests/test_merkle.py` in the
project environment. No real batch or public-chain verification is claimed by
these offline tests.

## Prepare, anchor, and verify batches

After producing real Gold classifications, snapshot hourly records:

```text
uv run --locked make anchor "ARGS=prepare --start 2026-10-05T00:00:00Z --end 2026-10-12T00:00:00Z"
```

Only confident `VALID` rows are selected. Empty hours are skipped. Canonical
snapshots and deterministic batch IDs persist in DuckDB, preserving old proofs
when Gold is rebuilt. The real run prepared 165 batches and 1,257 records.
Saved batches are not public anchors until a successful submission is recorded.

With `RPC_URL` and a funded throwaway `PRIVATE_KEY` in local `.env`, deploy with
`uv run --locked python contracts/script/deploy`. Use an ID returned by `prepare`
with `make anchor "ARGS=submit --batch-id BATCH_ID_FROM_PREPARE"`, then
`make anchor "ARGS=verify --batch-id BATCH_ID_FROM_PREPARE --index 0"`.

The client saves the signed transaction before broadcast and reuses it after
interruption. A successful receipt, matching event, and registry readback precede
marking a batch mined. Root and count come from the configured on-chain registry.
The October 24 run mined one of the 165 saved batches, containing seven records;
the other 164 remain saved only. See [actual receipts, commands, and recovery](../docs/ANCHORING.md)
and [contract setup](../contracts/README.md).

## Serve the API

```text
uv run --locked make api
```

Open <http://127.0.0.1:8000/docs> for interactive documentation. The API serves
stations, classified readings, events, batches, saved Merkle proofs, and record
verification. It starts without credentials; missing data/RPC produces explicit
errors. The real-data station, reading, event, batch and proof routes now return
data. Public verification works for the anchored demo batch. It reads the configured Sepolia registry
and needs no signing key. Decimal uploads retain precision through canonical
hashing; edited records fail when their canonical value changes.

Stop the API while running pipeline writers, then restart it. See
[endpoint schemas, filters, upload examples and error behavior](../docs/API.md).
Tests use synthetic data and an isolated local EVM; they do not establish public
testnet or real-air acceptance.

## Explore and verify in the frontend

With the API running in one terminal, start the frontend in another:

```text
uv run --locked make web
```

Open <http://127.0.0.1:5173>. Monitor shows station markers, selected wind context,
UTC observed/expected charts, nearby comparisons and saved event evidence. Choose
a prepared record to open Verify, inspect its canonical JSON and Merkle path,
then verify against the registry. Editing a record clears any previous verdict.
Evaluation displays the actual report and chart from `reports/`; blocked reports
never display invented scores. The current report contains measured scores and
the current plume-control result and confidence counts. The anchored demo record shows a public
verification success; editing its committed value produces a mismatch.

Frontend dependencies stay in `web/`. No backend secrets belong in `VITE_*`
variables. `npm run build` and `npm run preview` (from `web/`) provide a local
preview at port 4173 with the API still required. Stop readers before pipeline
writes. See [frontend setup, behavior and browser checks](../web/README.md).

## Honest limitations

The demo uses cached real observations with uneven coverage, not a live sampling
stream. Spike/drift/degradation detection remains weak. The development plume
control passes after an uncertainty safeguard; seven of eight affected rows
remain low confidence. Public anchoring currently covers one seven-record batch.
Weather is gridded reanalysis/model data, not a wind sensor at each
air-quality station. The detector can only mark an isolated spike as a
suspected fault: a local pollution source
may look similar. Evaluation explicitly labels injected faults and plume controls
as synthetic. Blockchain proofs establish that a record existed unchanged at
anchoring time; they cannot establish that the sensor reading was correct.
