# EcoProof HTTP API (task 9)

Run from the repository root after `uv sync --locked`:

```text
uv run --locked make api
```

This starts uvicorn at `http://127.0.0.1:8000`. Interactive Swagger UI is at
`/docs`, the OpenAPI document at `/openapi.json`, and ReDoc at `/redoc`.
Additional uvicorn arguments can be supplied through Make's `ARGS`, for example
`ARGS=--reload`. Direct equivalent:

```text
uv run --locked python -m uvicorn ecoproof.api.main:app --host 127.0.0.1 --port 8000
```

The service starts without a database or credentials, so documentation remains
available during setup. Data routes read the configured `ECOPROOF_DATA_DIR`.
Missing builds return HTTP 503; the API never substitutes synthetic observations.
The October 24 demo workspace serves 94 catalog locations, classifications at
11 locations, and saved proofs. One batch verifies against public Sepolia.
A fresh checkout contains no database and returns HTTP 503 from data routes
until observations are ingested and Silver/Gold are built; `/docs` still works.
See [the current demo](DEMO.md) and [fresh-checkout handoff](HANDOFF.md).

Verification needs a Sepolia `RPC_URL`, `REGISTRY_ADDRESS` (or the mined deployment
journal), and the compiled contract artifact. See [anchoring setup](ANCHORING.md).
It does **not** need `PRIVATE_KEY`. No endpoint deploys, submits transactions,
changes data, or exposes signing keys, RPC URLs, or saved raw transactions.
The default registry client pins chain ID **11155111**; clients cannot choose an
RPC URL, chain, contract, trusted root, or trusted count through request fields.

## Responses and filters

All GET list endpoints return JSON arrays. Timestamps are ISO 8601 UTC strings
ending in `Z`. Query timestamps require seconds and an explicit `Z` or offset;
date-only, naive, numeric epoch, and over-six-digit fractional inputs are rejected.
Hashes of records, roots and siblings are lowercase 64-character hex without
`0x`. Transaction hashes retain Ethereum's `0x` prefix.

| Route | Behavior |
| --- | --- |
| `GET /stations` | Station ID, name, latitude/longitude, provider, cluster ID, and `latest` classification. Ordered by station ID. `latest: null` means no current classification is available; it is not a healthy label. |
| `GET /readings?station=…&from=…&to=…` | Current hourly Gold classifications for one station in `[from,to)`, ordered oldest first. Requires `from < to`; maximum window 31 days. No matching rows returns `[]`. Does not fill gaps or substitute raw Silver samples. |
| `GET /events?label=…&limit=100` | Recent `SENSOR_FAULT_DRIFT` and `VERIFIED_PLUME_EVENT` rows. Optional `label` must be one of those two. Limit 1–1000, newest timestamp first, then station ID. |
| `GET /batches?limit=100&offset=0` | Saved batches, newest window first, then batch ID. Limit 1–1000; offset 0–100000. Includes `merkle_root`, count, UTC window, mined `tx_hash`, `chain_id`, `anchored_at`, and submission `contract_address` when available. |
| `GET /proof?station=…&ts=…&batch_id=…` | Canonical record and path from a retained batch snapshot. `batch_id` is optional; without it, select the batch linked to the matching **current** Gold hash. |
| `POST /verify` | JSON record upload with `batch_id`, zero-based sorted `leaf_index`, and optional `path`; checks the configured registry on every valid verification request. See below. |

Each reading includes value, expected value, residual, z, label, neighbor count,
wind speed/direction, `record_hash`, nullable `batch_id`, `low_confidence`, reason,
baseline sigma, and smoothed z. Concentrations use µg/m³; wind uses m/s and
meteorological degrees **from** north, clockwise. Hourly timestamps label the
interval ending at that time; query bounds select those labels.

Events also expose saved `plume_evidence` and `plume_sources`. A plume neighbor
entry includes station, UTC time, lag, travel time, alignment, rise, and its
recent reference value. Empty evidence remains empty. The detector does not save
a separate per-neighbor measurement list for faults; those rows expose the saved
neighbor count and reason. These API responses do not invent additional evidence.

`VALID` with `low_confidence: true` is not verified healthy. A fault label means
suspected fault, since a local pollution source can look similar. The detector
uses later observations for retrospective plume classification.

Batch listings describe saved state, not a fresh chain check. Null mined fields
mean no confirmed anchor is recorded locally, including a possibly pending
submission. A pending submission can already have a contract address. Only
`POST /verify` consults the chain. Receipt/readback is mined inclusion, not
irreversible finality. Explorer links can be formed for an actual returned
Sepolia transaction; do not label test chain 31337 transactions as Sepolia.

## Proofs and record uploads

`GET /proof` returns:

- `batch`: the metadata described above.
- `leaf_index`: zero-based position after sorting by station ID and UTC timestamp.
- `record`: the twelve-field committed payload from [MERKLE.md](MERKLE.md).
- `canonical_record`: the exact UTF-8 JSON string with four-decimal numbers.
- `record_hash`, `root`, and `path`: sibling objects with `sibling_hash` and `side`
  (`left` or `right`), ordered from leaf to root.

Only confident `VALID` records currently enter batches. Other current records,
missing records, or records not yet prepared return 404 for a default proof.
After a rebuild changes a record, the default lookup will not return its old
proof. Supply the old `batch_id` explicitly to retrieve that retained snapshot,
even when current Gold views are absent. Preparation validates the snapshots;
the API validates their root, count, indices, keys, hashes and window again.

Use a station/time returned by `/readings` with a non-null batch ID. This runnable
client takes those values as arguments; no sample station or public transaction
is claimed:

```python
# Save as a local helper, then: python helper.py STATION_ID UTC_TIMESTAMP
import sys
import httpx

with httpx.Client(base_url="http://127.0.0.1:8000", timeout=90) as client:
    response = client.get("/proof", params={"station": sys.argv[1], "ts": sys.argv[2]})
    response.raise_for_status()
    proof = response.json()
    upload = {
        "batch_id": proof["batch"]["batch_id"],
        "leaf_index": proof["leaf_index"],
        "record": proof["record"],
        "path": proof["path"],
    }
    response = client.post("/verify", json=upload)
    response.raise_for_status()
    print(response.json())
    upload["record"]["value"] += 0.0001
    response = client.post("/verify", json=upload)
    response.raise_for_status()
    print(response.json())
```

Uploads use `Content-Type: application/json` and a JSON object, not multipart.
Do not put derived `record_hash` or `batch_id` inside `record`. Extra fields,
duplicate JSON keys, non-finite numbers, numeric strings, and boolean-as-number
coercions are rejected. The body limit is **64 KiB**, including whitespace.
Decimal JSON tokens retain their exact decimal value before half-even rounding.
The four-decimal canonical string is authoritative; normal JSON response numbers
are for display and may omit trailing zeroes. Edits that round to the same
four-decimal value intentionally verify identically.

If `path` is omitted or null, the server rebuilds it from the retained snapshot.
If supplied (including an empty single-leaf path), it is checked instead. The
server still validates the snapshot and compares its root, count and window to
the trusted on-chain batch. Neither an uploaded path nor local metadata supplies
the trusted root/count. A stored submission for a different chain/registry
returns 409. No local success is used as a fallback during an RPC failure.

HTTP 200 verification results contain `verified`, `code`, `reason`, batch/index,
the uploaded `record_hash`, `on_chain_root`, on-chain `record_count`, chain ID,
contract address, on-chain anchor time, and locally confirmed transaction hash
(which may be null if mining occurred but local receipt reconciliation has not).

| Code | Meaning |
| --- | --- |
| `verified` | Canonical payload and path match the on-chain root and count. This establishes record integrity, not sensor correctness. |
| `unanchored` | No anchor exists for that batch in the configured registry. Root/time are null; count is zero. |
| `batch_mismatch` | Saved root, time window or count disagrees with the chain. |
| `record_mismatch` | Uploaded record or supplied path fails inclusion verification. |

## Failures and local operation

Errors have a JSON `detail` string. Malformed fields/body return 422, excessive
body size 413, unsupported content type 415, unknown batch/record/index 404,
inconsistent saved snapshots or registry binding 409, and unavailable/missing
data or chain 503. A 503 is **not** a tamper verdict. Provider exception text and
uploaded values are excluded from error responses.

Each request opens and closes a read-only DuckDB connection and uses one database
snapshot; it does not create tables. Verification closes the database before RPC
calls. DuckDB does not support an external writer while another process holds a
read connection: stop serving during ingestion/build/detection/anchoring, then
restart the API. A lock conflict returns 503. Multiple concurrent readers are
allowed. This is the local MVP service; authentication and public deployment are
outside task 9. Task 10's Vite dev/preview proxy forwards `/api/*` to these existing
routes without adding broad CORS access or frontend credentials. Its evaluation
JSON/PNG are static report assets, not additional FastAPI endpoints.

## Documentation checked

- [FastAPI response models](https://fastapi.tiangolo.com/tutorial/response-model/)
- [FastAPI testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [Custom Request and APIRoute](https://fastapi.tiangolo.com/how-to/custom-request-and-route/)
- [Pydantic standard types, Decimal strictness and serialization](https://docs.pydantic.dev/latest/api/standard_library_types/)

Checked the projects' official GitHub documentation sources as well as installed
library behavior. FastAPI's testing documentation uses HTTPX; installed Starlette
1.9.0 supports it but emits a deprecation warning recommending `httpx2`. The
existing project HTTPX dependency is retained and the warning is not hidden.
