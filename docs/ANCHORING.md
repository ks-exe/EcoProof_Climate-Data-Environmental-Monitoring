# Hourly batches and Ethereum Sepolia anchoring

Task 8 implements the contract, deployment tool, batch storage, and web3.py
submit/read/verify operations. The **October 24 public testnet demonstration
passed**: the registry was deployed and one seven-record Gold batch was mined on
Ethereum Sepolia. The CLI and browser accepted the original record and rejected
an edited value; restoring it passed in the browser. The private key remains in
ignored `.env`. Local EVM tests are separate from this public evidence.

## Actual public evidence

- Registry: [`0xb120d4671607E7C24F6C14C4f23B589F5f4484EB`](https://sepolia.etherscan.io/address/0xb120d4671607E7C24F6C14C4f23B589F5f4484EB).
- [Deployment transaction](https://sepolia.etherscan.io/tx/0x4a57758efaa4c467b8becb82625e6084a8fc2b054d5ffb01c0945d6d38482b67): block 11981959, gas used 2,112,789.
- [Anchor transaction](https://sepolia.etherscan.io/tx/0xbc325583e39e7778538a69878d9507281444a2e508ce13f048df455096ca5e49): block 11981966, gas used 239,742, anchored at 2026-10-24 06:16:24 UTC.
- Both receipts have status 1. The anchor event, canonical block header, registry
  root, time bounds and count match the immutable local batch.
- Batch: `ecoproof:v1:valid:20261011T230000Z:e7aaf8938d201639002bfed699ed30b73674746c28d460ad4f1ce594aa67efc0`.
- Station 17 (R K Puram), 2026-10-11 23:00 UTC, leaf index 0: value **22.0000**
  verifies; **23.0000** fails. Restore the saved value to verify again.
- [Receipt and CLI evidence](../reports/sepolia-demo.json),
  [original payload and Merkle path](../reports/sepolia-proof.json),
  [actual API/browser verdicts](../reports/demo-browser.json), and
  [demo walkthrough](DEMO.md) retain the measured results.

Only this batch is publicly anchored. The remaining 164 are saved locally.
Registry verification establishes record integrity, not sensor or model accuracy.

For the published sample, `uv run --locked python scripts/verify_public_demo.py`
reads Sepolia and verifies `reports/sepolia-proof.json` without a local database
or private key. Add `--tamper` for an in-memory edit that must fail with exit 1.
Python dependencies, the compiled contract artifact and `RPC_URL` are required.
See [the independent check](HANDOFF.md#verify-the-public-sample-without-the-operators-database).

## Setup and commands

Install the Python lockfile with `uv sync --locked`. Install Node 22.13+ and run
these commands **inside `contracts/`**:

```text
npm ci
npm test
npm run compile
```

PowerShell users can use `npm.cmd` to avoid the script execution policy on the
`npm.ps1` shim. Return to the repository root and run Python in `.venv`, or prefix
commands with `uv run --locked`. Python integration tests require the contract
dependencies; they compile the registry automatically and fail if tooling is
missing instead of silently skipping contract coverage.

Local `.env` settings:

| Setting | Purpose |
| --- | --- |
| `RPC_URL` | An Ethereum Sepolia HTTP RPC endpoint. No implicit provider fallback. |
| `PRIVATE_KEY` | Funded throwaway Sepolia wallet; used only for deployment/submission. |
| `REGISTRY_ADDRESS` | Optional explicit contract address. Otherwise use the mined local deployment journal. |
| `ECOPROOF_DATA_DIR` | Existing data root, default `data`. |

The public CLI enforces chain ID **11155111**. Read and verify operations do not
need a private key. RPC errors are sanitized because provider errors can contain
URLs with embedded API credentials. `.env.example` documents the settings; never
copy private values into frontend configuration or public reports.

Prepare observed hourly Gold records without a network call:

```text
make anchor "ARGS=prepare --start 2026-10-05T00:00:00Z --end 2026-10-12T00:00:00Z"
```

These example dates require real data, a prior calibration window, and Gold
classification first. The current real workspace has 1,257 confident VALID
records prepared into 165 hourly batches; one seven-record batch is publicly anchored.

Deploy the compiled contract, or resume the same deployment after an interruption:

```text
make anchor ARGS=deploy
python contracts/script/deploy
```

These are equivalent entry points; one is sufficient. Deployment stores a local
journal before sending and then records the mined contract address, transaction
hash, block number/hash, owner, actual gas used, and compiled bytecode fingerprint.
Repeat invocations reuse the journal and transaction; they do not silently deploy
another registry. An explicit `REGISTRY_ADDRESS` overrides journal address lookup.

Use an actual ID printed by `prepare` in the following commands:

```text
make anchor "ARGS=submit --batch-id BATCH_ID_FROM_PREPARE"
make anchor "ARGS=read --batch-id BATCH_ID_FROM_PREPARE"
make anchor "ARGS=verify --batch-id BATCH_ID_FROM_PREPARE --index 0"
make anchor "ARGS=verify --batch-id BATCH_ID_FROM_PREPARE --index 0 --record edited-record.json"
```

Submit sends **one** batch. Verify uses a zero-based sorted leaf index and reads
the root and count from the configured registry. The optional JSON file must be
exactly the twelve-field [Merkle payload](MERKLE.md); duplicate JSON keys are
rejected. A mismatch exits nonzero. There is no API endpoint in this task.

## Gold storage and rebuild behavior

Gold classification now computes a canonical `record_hash` for every label.
The `classified.parquet` hash column is reproducible from the classifier output;
its batch ID is resolved in the DuckDB view from the retained batch snapshots.
Pre-task-8 Gold files with null hashes must be rebuilt using `make detect`.

`prepare` reads one Gold/evidence snapshot and selects only `label = 'VALID' AND
low_confidence = false`. Missing evidence or inconsistent hashes fail the entire
requested window. Other-label batches are optional in the spec and are not
enabled. Empty hours are skipped; an entirely empty selection exits nonzero.

Batch time bounds are `[classification timestamp, timestamp + 1 hour)`. Gold's
hourly timestamp represents samples ending at that time; a batch window identifies
the classification hour, not the underlying samples' acquisition interval.

Each batch ID is:

```text
ecoproof:v1:valid:YYYYMMDDTHHMMSSZ:ROOT_HEX
```

The identifier includes the root so changed classifications produce a new batch
revision. The contract key is **Keccak-256 of the UTF-8 batch ID**, using
`Web3.keccak(text=batch_id)`. Merkle leaves/parents continue to use SHA-256.

DuckDB storage retains the spec's `gold.batches` columns and adds two companion
tables without changing `docs/SPEC.md`:

- `gold.batch_records`: immutable canonical strings, sorted indices, station/time
  keys, and leaf hashes, keyed by batch and index. These preserve complete proof
  payloads when later Gold Parquet builds replace current readings/classifications.
- `gold.anchor_submissions`: chain ID, registry address, transaction hash, and
  signed transaction bytes, persisted before sending. The signed bytes contain
  no private key and allow resuming the same transaction.

Batch metadata and canonical records publish together in one DuckDB transaction.
Identical batches are checked and reused; snapshots are never overwritten.
On loading, the code reconstructs the root and checks count, canonical strings,
indices, keys, eligibility, window, and ID. Corruption causes an error.

`gold.classified.batch_id` joins by station, timestamp, and committed record hash.
A changed record does not inherit an old proof. If an unchanged record occurs
in several revisions, the view chooses one link, preferring mined batches, then
anchor time and batch ID. It never duplicates classification rows. A link to a
prepared batch is not a claim that the batch was anchored; inspect `tx_hash` and
`anchored_at`. `make detect --rebuild-silver ...` retains prior batch history while
rebuilding current classifications from Bronze.

Back up the DuckDB database and deployment journals along with raw data. Chain
receipts and transaction history are external provenance, not derivable solely
from Bronze. Deleting these local snapshots/journals is not a rebuild step.

## Submission, verification, and recovery

Before signing, the client checks chain identity, registry code, owner, pending
nonce, and available wallet balance. Gas and fee values come from the RPC, with
20% gas-limit headroom. No fee/gas result is invented or hardcoded as a measurement.
Contract calls and deployment transfer zero ETH value apart from network gas.

Signed intent is saved **before broadcast**. A retry first looks for the saved
hash, waits if it is pending, or rebroadcasts the same bytes if the node has not
seen it. A lost response cannot cause an automatic new nonce or new deployment.
The receipt must have status 1, the expected hash, and a canonical block header.
For anchoring, its contract and event must match; the current registry root,
window, count, and anchor timestamp must match the local batch and receipt header.
Only then are the spec's `gold.batches.tx_hash`, `chain_id`, and `anchored_at` set.
Current state plus event/header checks avoid historical `eth_call` archive access.

Timeouts and network errors keep the saved intent. Rerun the same command to
resume. Reverted transactions, externally replaced nonces, conflicting registry
addresses, or an on-chain key with no local submission require inspection of the
original transaction; there is no automatic fee replacement or journal deletion.
Use one submitting process per wallet. The write connection prevents competing
writer processes on the same DuckDB file, but cannot coordinate another wallet
application or a different data directory.

`mined` means a successful inclusion receipt and readback, not irreversible chain
finality. Later verification reads the registry again, so a reorg removing the
commitment does not receive a positive result merely from cached database metadata.
An auditor must trust the configured chain/registry identity and RPC response.
The commitment protects the canonical four-decimal payload; it cannot prove that
the sensor, classifier, or operator was correct.

## Documentation checked

- [Hardhat configuration](https://hardhat.org/docs/reference/configuration) and
  [built-in Solidity tests](https://hardhat.org/docs/guides/testing/using-solidity).
  Also checked installed 3.20.0 source for compiler paths, explicit file builds,
  artifact generation, and Node 22.13 minimum support.
- Official web3.py [transaction guide source](https://github.com/ethereum/web3.py/blob/main/docs/transactions.rst),
  [contract reference source](https://github.com/ethereum/web3.py/blob/main/docs/web3.contract.rst),
  and [Eth reference source](https://github.com/ethereum/web3.py/blob/main/docs/web3.eth.rst).
  ReadTheDocs returned HTTP 403 inside and outside the sandbox, so its official
  GitHub sources and the installed 7.16.0 signatures were used. Signing,
  receipt handling, events, and readback were exercised against the local EVM.
- [Ethereum chain registry entry for Sepolia](https://github.com/ethereum-lists/chains/blob/master/_data/chains/eip155-11155111.json)
  for chain identity and the Sepolia Etherscan explorer. No placeholder
  transaction or explorer link is presented as an actual result.
