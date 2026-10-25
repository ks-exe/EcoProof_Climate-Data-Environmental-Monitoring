# Merkle record and proof format — v1

Task 7 implements `ecoproof.provenance.merkle` with the Python standard library.
It builds and verifies local inclusion proofs. Task 8 adds [hourly batch storage
and on-chain submission/readback](ANCHORING.md). There are no real air-data batches
or public testnet transactions yet.

## Committed payload

Pass a mapping containing **exactly** these fields:

| Fields | Canonical representation |
| --- | --- |
| `station_id` | Nonblank string; exact spelling, case, and Unicode retained. |
| `ts` | UTC ISO timestamp with six fractional digits, ending in `Z`. |
| `value` | Finite JSON number with exactly four decimal places. |
| `expected`, `residual`, `z`, `wind_speed`, `wind_dir_deg` | Four-decimal finite JSON numbers, or `null` when unavailable. |
| `label` | `VALID`, `SENSOR_FAULT_DRIFT`, or `VERIFIED_PLUME_EVENT`. |
| `neighbor_count` | Nonnegative integer, never a boolean or float. |
| `low_confidence` | Boolean from classification evidence. |
| `reason` | Nonblank string from classification evidence. |

The ten data columns come from `gold.classified`; `low_confidence` and `reason`
come from `gold.classification_evidence`, joined by `(station_id, ts)`. Project
these twelve fields explicitly. `record_hash` and `batch_id` are derived metadata
and excluded to avoid a circular hash. Unknown or missing fields raise
`ValueError`, so metadata is never silently ignored during verification.
The payload does not commit station metadata, full classifier evidence, baseline
configuration, original Bronze bytes, or arbitrary extra fields.

This payload includes the confidence fields without changing the spec's Gold
table schema. The existing schema proposal is in [CLASSIFIER.md](CLASSIFIER.md).
`docs/SPEC.md` is unchanged. Future changes to this byte contract must use a new
documented format; reinterpreting old roots with a new schema will invalidate proofs.

## Canonical bytes

- Keys sort lexicographically. JSON has no insignificant whitespace or final
  newline. Spaces inside strings remain significant.
- String quoting/escaping uses Python `json.dumps(..., ensure_ascii=False)`;
  non-ASCII characters are UTF-8, with no Unicode normalization. Invalid Unicode
  surrogate characters are rejected.
- All six numeric data fields use four-decimal **JSON numbers, not strings**.
  Integers supplied in those fields normalize to the same bytes as equivalent
  floats, e.g. `12`, `12.0`, and `Decimal("12.0000")` become `12.0000`.
  Numeric strings and booleans are rejected. Nonfinite values and magnitudes
  exceeding finite DOUBLE range are rejected.
- Rounding is decimal **round half to even**. Python floats first use their
  shortest decimal string (`Decimal(str(value))`). An explicit Decimal context
  makes rounding independent of caller precision/rounding settings. Examples:
  `1.23445` becomes `1.2344`; `1.23455` becomes `1.2346`. Negative rounded zero
  becomes `0.0000`. Scientific notation is never emitted.
- Timestamps accept timezone-aware Python datetimes or ISO strings with seconds,
  an explicit `Z`/`±HH:MM` offset, and at most six fractional digits. They normalize
  to UTC, e.g. `2026-10-21T05:00:00+05:00` becomes
  `2026-10-21T00:00:00.000000Z`. Dates, naive times, leap seconds, and excess
  fractional precision are rejected. Gold's naive DuckDB `TIMESTAMP` has known
  UTC meaning: its adapter must explicitly attach `timezone.utc`, never infer
  the computer's local timezone.

`canonical_record(record)` returns that string; `hash_record(record)` returns
32 raw bytes. The library validates payload shape and serializability; it does
not rerun sensor validation or certify classifier output. For exact parsing of
canonical JSON, use `json.loads(text, parse_float=Decimal)`, especially when
values exceed floating-point decimal precision. A future HTTP reader must also
reject duplicate JSON keys before creating a mapping; collapsed keys cannot be
detected afterward by this mapping-based library.

Four-decimal rounding deliberately means some source changes share a hash.
For example, `12.5` and `12.50001` both encode as `12.5000`; `12.5001` differs.
These proofs protect the **canonical payload**, not every bit of the source
DOUBLE or the source's original timestamp/text formatting.

## Tree and path rules

`MerkleTree(records)` sorts by `(station_id, UTC ts)`. Station IDs sort as text,
so `"10"` precedes `"2"`. Fixed-width UTC timestamps sort chronologically. Input
order and mapping-key order cannot change the root or leaf indices. Duplicate
keys, including equivalent timestamps with different offsets, are rejected;
an empty tree is rejected. A single leaf is its own root and has an empty path.

Domain separation follows the spec's recommended hardening:

```text
leaf   = SHA256(0x00 || UTF8(canonical_record))
parent = SHA256(0x01 || left_32_bytes || right_32_bytes)
```

At **every** odd level, the final node is duplicated. Hash bytes are concatenated
directly; hex text is only a storage/transport representation. The tree retains
immutable canonical strings and hash tuples, so later caller edits do not change
the snapshot. Access `keys`, `canonical_records`, `leaf_hashes`, `root`, and
`record_count` on the tree.

`tree.proof(index)` returns `MerkleProof(leaf_index, path)` for the zero-based
**sorted** index. `path` is an immutable tuple of `(sibling_bytes, side)` pairs
from leaf to root. `side` is the sibling's position: `left` means hash sibling
before the current digest; `right` means hash it afterward. JSON transport can
represent it as `[[sibling.hex(), side], ...]`; reconstruct raw 32-byte values
and tuples before verification. Future API response models belong to task 9.

```python
verify_proof(record, proof, trusted_root, record_count=trusted_count)
```

Verification returns `False` for malformed records/hashes/paths, wrong ordering,
out-of-range indices, truncated/extra paths, incorrect odd-node duplication, or
a different reconstructed root. `canonical_record`, `hash_record`, tree
construction, and proof lookup raise `ValueError` for invalid inputs instead.

**The root and count must come from the same trusted batch.** Odd duplication
means the root of `[a, b, c]` is also the root of `[a, b, c, c]`. A proof cannot
authenticate cardinality by the root alone. The verifier requires a separate
trusted count to check index, side, path depth, and padding. Some proofs can fit
more than one count; accepting a caller's claimed count does not authenticate it.
The task 8 client reads both root and count from the registry; an uploaded proof's root
and count are not trust sources.

The generic tree includes every supplied payload and hashes its label and
confidence. It does not silently filter data. Task 8's validated-data batching
selects `label = 'VALID' AND low_confidence = false` using the evidence join and
skips empty hours. Other-label batches are not enabled. Inclusion never
establishes sensor truth.

## Offline synthetic example

Run this in the project Python environment. These values are a software example,
not ingested observations or an anchored batch:

```python
from decimal import Decimal
import json
from ecoproof.provenance.merkle import MerkleTree, verify_proof

sample = {
    "station_id": "a", "ts": "2026-10-21T00:00:00Z", "value": 12.5,
    "expected": 12, "residual": 0.5, "z": 0.25, "label": "VALID",
    "neighbor_count": 2, "wind_speed": 2, "wind_dir_deg": 270,
    "low_confidence": False, "reason": "synthetic fixture",
}
tree = MerkleTree({**sample, "station_id": station} for station in ("c", "a", "b"))
payload = json.loads(tree.canonical_records[1], parse_float=Decimal)
proof = tree.proof(1)
print("record_count:", tree.record_count)
print("root:", tree.root.hex())
print("original:", verify_proof(payload, proof, tree.root, record_count=3))
payload["value"] = Decimal("12.5001")
print("tampered:", verify_proof(payload, proof, tree.root, record_count=3))
```

Actual output from running that example on October 21, 2026:

```text
record_count: 3
root: 4a268ccda76b4ec0489967f57f937549828142027b20b651ae3e05056c3428d6
original: True
tampered: False
```

The root in this example is trusted only because it was just computed locally.
No blockchain verification is implied by this example. Task 8 computes Gold
record hashes and resolves batch links against persisted canonical snapshots;
see [ANCHORING.md](ANCHORING.md).
