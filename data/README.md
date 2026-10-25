# Local data

- `bronze/`: immutable raw API JSON envelopes, named `{source}_{UTC-timestamp}.json`.
- `silver/build-*/`: validated, deduplicated Parquet with UTC timestamps and a build report.
- `gold/build-*/`: classified Parquet, confidence/evidence Parquet, and build reports.
- `ecoproof.duckdb`: runtime database with the three `silver.*` views and, after detection, `gold.classified` and `gold.classification_evidence`.
- The database also retains `gold.batches`, immutable canonical `gold.batch_records`, and durable `gold.anchor_submissions` after task 8 setup.
- `deployments/sepolia.json`: local deployment transaction journal, created only when deployment prerequisites are available.

Only directory placeholders and this document are tracked. Real pulls, rebuilt
Parquet files, build reports, and the database are local and ignored by Git.
`ECOPROOF_DATA_DIR` can point to another local data directory. Never modify a saved Bronze pull.

Each Bronze envelope stores `schema_version`, `source`, `fetched_at`, `request`
(URL, parameters, and nonsecret context), and the provider's JSON under `response`.
Readings are not cleaned or rounded during ingestion. See
[`docs/INGESTION.md`](../docs/INGESTION.md) for the precise cache contract.

Use `make build ARGS="--region delhi"` in the activated environment to rebuild
Silver from local Bronze. Add paired `--start-date` and `--end-date` arguments to
restrict the UTC window. The database views select the latest published build;
do not combine all build directories in a Parquet glob. Previous builds are kept,
and a failed publication leaves the previous views intact.

`make detect ARGS="..."` builds Gold from Silver with explicit baseline and output
windows. Add `--rebuild-silver` to rebuild from Bronze in the same command. Read
[`docs/CLASSIFIER.md`](../docs/CLASSIFIER.md) for hourly aggregation and confidence
rules. Join classification rows with their evidence; low-confidence `VALID` rows
are not verified healthy data. Gold builds now compute canonical hashes; batch
IDs link only to matching saved snapshots. Batch snapshots and submission/deployment
journals preserve history across Gold rebuilds and should be backed up. See
[`docs/ANCHORING.md`](../docs/ANCHORING.md). The October 23 real run contains Delhi
air observations, 1,546 Gold classifications and 165 prepared hourly batches.
On October 24, the funded test wallet deployed the registry and anchored one
seven-record batch on public Sepolia. Read-only verification needs an RPC, not
another wallet funding or deployment. See the public evidence in `reports/`.
