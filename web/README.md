# EcoProof frontend (task 10)

React, TypeScript, Vite and Leaflet. Three views implement spec section 8:
Monitor (map, station chart and events), Verify, and Evaluation. There is no
synthetic-data switch or placeholder metric in the application. The October 24
workspace contains real Delhi observations, classifications, saved proofs and a
completed evaluation. Its plume control now passes (0/8 false faults), with 7/8
affected observations low confidence; other fault scores remain weak. One
seven-record batch is publicly anchored on Sepolia; the original/edited/restored
browser verification returns true/false/true. See [the current demo](../docs/DEMO.md).

## Run locally

Use Node **22.13+** (22.20.0 was used here) and the root Python environment.
Install the locked frontend packages from this directory:

```text
npm ci
```

From the repository root, run these in separate terminals:

```text
uv run --locked make api
uv run --locked make web
```

Open **http://127.0.0.1:5173**. API documentation is at
http://127.0.0.1:8000/docs. On PowerShell use `npm.cmd` when calling npm directly;
the root Makefile selects it automatically on Windows.

The equivalent frontend command, from `web/`, is `npm run dev`. For a production
build and a **local** preview:

```text
npm run build
npm run preview
```

Preview listens on http://127.0.0.1:4173 and also needs the API running. Both Vite
servers bind to loopback, require their port to be free, and proxy `/api/*` to
the existing FastAPI routes at `http://127.0.0.1:8000` (removing `/api`). No new
FastAPI endpoints, broad CORS settings, or frontend credentials are required.

If the API uses a different local port, set the **server-only**, non-secret
`ECOPROOF_API_ORIGIN` process variable before starting dev/preview, for example:

```powershell
$env:ECOPROOF_API_ORIGIN = "http://127.0.0.1:8001"
npm.cmd run dev
```

Only local HTTP origins without credentials or paths are accepted. The Vite
configuration does not load the repository-root `.env`. Keep `OPENAQ_API_KEY`,
`RPC_URL`, and `PRIVATE_KEY` in that backend environment; **never copy secrets
into `VITE_*` variables**. Public hosting is outside this task. A future static
host must serve the build and route `/api/*` to the backend itself; a directory
of static assets alone does not provide the API.

Stop serving while running pipeline/anchoring writers, then restart the API.
DuckDB cannot accept an external writer while a reader process holds a connection.

## Monitor

- Station counts and markers come from `/stations`. Colors distinguish Valid,
  Suspected fault, Plume evidence, Low confidence, and No classification. Counts
  describe each station's latest saved classification, not live sampling or field
  accuracy. A missing classification is never displayed as a healthy reading.
- Select a marker by mouse or keyboard, or use the searchable station list.
  Leaflet uses OSM tiles and preserves attribution. Tile failures are disclosed;
  markers and the list still work. Tiles require internet; no tiles are fabricated
  or bulk downloaded.
- The selected station's wind arrow points **toward** `(wind_from + 180) % 360`.
  Speeds are m/s. Calm/missing wind is stated without inventing a direction.
  Wind is the pipeline's model/reanalysis context, not a wind sensor at each site.
- Hourly charts show observed and expected PM2.5, with selectable nearby context.
  Initial bounds cover the 24 hours ending just after the selected/latest hour;
  all controls and labels are UTC. Bounds are half-open and capped at 31 days.
  Missing hours and null expected values break lines instead of being filled.
- The comparison selector uses coordinates to find stations within 20 km in the
  same cluster. It explicitly describes **geographic context**, not the exact
  graph used for a classification (which the current API does not expose).
  Select a nearby station to fetch its actual series for the same window.
- Select an observed row to inspect value, expected value, residual z, usable
  neighbor count, wind and saved reason. Only a row with a prepared `batch_id`
  enables the record-proof action.
- Event filters show saved fault/plume rows with wind, reason, neighbor count,
  and any saved plume/source evidence. An isolated spike is a **suspected** fault;
  a local source can look similar. Low-confidence VALID is not verified healthy.

## Verify

Open a reading from Monitor, or choose a saved batch and enter a station ID and
ISO timestamp (seconds plus timezone). An explicit batch ID requests retained
history; a blank one asks for the proof linked to the current Gold hash. Enter
historical station IDs directly if they no longer appear in the station list.

The page displays the canonical JSON, leaf hash, saved root, and ordered sibling
path. The leaf position shown to the user starts at 1; the API still uses its
documented zero-based `leaf_index`. Saved/mined badges come from local metadata;
only **Verify record** reads the configured registry.

Edit the JSON or upload a replacement JSON file. The exact text is embedded in
the POST body without JavaScript parsing/reserialization, preserving decimal
precision and duplicate keys for backend validation. Extra fields or invalid
types are rejected by FastAPI; the page does not silently normalize them. See
[the API contract](../docs/API.md) and [canonical format](../docs/MERKLE.md).

A successful API result displays a green confirmation. Record/path mismatches
display failure; missing anchors and unavailable services stay distinct. Any
edit or selection change immediately clears a prior verdict and aborts/ignores
obsolete responses. Restore the saved record to repeat the check. Differences
that round to the same four decimals intentionally share a proof.

Transaction links are constructed only for a returned Sepolia chain ID and
properly formed transaction hash. Local chain 31337 is explicitly labeled and
gets no misleading public explorer link. Proofs establish canonical record
integrity at anchoring time, not sensor truth or irreversible finality.

## Evaluation assets

The page reads **the existing `reports/eval.json` and its referenced PNG**.
`scripts/reports.ts` serves these two files in development and includes their
unchanged bytes in `dist/reports/` at build time. It only accepts the evaluator's
`eval-<32 lowercase hex>.png` filenames and checks the PNG signature. Arbitrary
repository files, path traversal, private keys and `.env` are not exposed.

Refresh the page's report after a development evaluation run. Production/preview
assets are a build snapshot: rebuild after publishing a new evaluation. An
absent, unreadable, or invalid report/chart produces an unavailable state rather
than a replacement dataset. A blocked report displays the generated status chart
and **no metric table**. A complete report displays its measured per-type and
per-method precision/recall/F1; null ratios remain undefined. Faults and plume
controls are always labeled synthetic interventions.

## Tests and browser prerequisites

From `web/`:

```text
npm test
npm run build
```

From the root, after installing/compiling the contract tools as documented in
the main README:

```text
uv run --locked pytest -q -s tests/test_web.py
uv run --locked pytest -q
```

Browser acceptance is part of the Python suite. It requires an installed Chrome
and the built frontend; missing tooling fails explicitly. It starts and stops
its own temporary Vite preview, FastAPI server and EVM, injects **synthetic test
data** into a separate DuckDB directory, and invokes the Playwright suite in
`browser/`. Successful checks use actual HTTP and contract execution. Specific
error-state tests intercept responses, and OSM tiles are deliberately blocked
to exercise the fallback without relying on external tile delivery. It does not
write synthetic observations into the real workspace or submit public transactions.

`ECOPROOF_BROWSER_CHANNEL=msedge` selects an installed Edge. For a bundled browser,
install it with `npx playwright install chromium` from `web/`, then set
`ECOPROOF_BROWSER_CHANNEL=chromium`. These alternatives follow Playwright's
documented channel support; this task's execution used installed Chrome.

`npm run test:browser` expects the synthetic fixture URLs/configuration supplied
by the Python test; it deliberately refuses to run fixture assertions against
an arbitrary real server. Screenshots, failed traces and raw UTF-8 browser output
are in ignored `web/test-results/`. The actual execution history and limits are
recorded in [PROGRESS.md](../docs/PROGRESS.md).

## Documentation checked

- [Leaflet 1.9.4 quick start](https://github.com/Leaflet/Leaflet/blob/v1.9.4/docs/examples/quick-start/index.md)
- [Vite server proxy](https://vite.dev/config/server-options.html#server-proxy)
- [Vite plugin hooks and asset emission](https://vite.dev/guide/api-plugin.html)
- [React effects and cleanup](https://react.dev/reference/react/useEffect)
- [Playwright browser channels](https://playwright.dev/docs/browsers)

Versions and Node compatibility were checked in the npm registry. Leaflet's
installed source was checked for keyboard/popup behavior. Setup choices and
frontend wire handling leave `docs/SPEC.md` unchanged.
