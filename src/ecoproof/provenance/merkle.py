"""Canonical Gold payloads and SHA-256 inclusion proofs (spec section 7).

The wire format and precision limits are documented in docs/MERKLE.md. This
module does not select validated records, publish batches, or contact a chain.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Context, Decimal, ROUND_HALF_EVEN
from hashlib import sha256
import json
import math
import re
from typing import Literal


FLOAT_FIELDS = frozenset({"value", "expected", "residual", "z", "wind_speed", "wind_dir_deg"})
RECORD_FIELDS = FLOAT_FIELDS | {
    "station_id", "ts", "label", "neighbor_count", "low_confidence", "reason",
}
LABELS = frozenset({"VALID", "SENSOR_FAULT_DRIFT", "VERIFIED_PLUME_EVENT"})
_ISO_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)
Side = Literal["left", "right"]
RecordKey = tuple[str, str]


def _utc_timestamp(value: object) -> str:
    if isinstance(value, str):
        if not _ISO_TIMESTAMP.fullmatch(value):
            raise ValueError("ts must be an ISO timestamp with seconds and an explicit timezone")
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("ts must have an explicit timezone; attach UTC to Gold TIMESTAMP values")
    try:
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    except (ValueError, OverflowError) as exc:
        raise ValueError("ts is outside the supported UTC datetime range") from exc


def _fixed_number(value: object, field: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{field} must be a finite number")
    number = Decimal(str(value))
    if not number.is_finite() or not math.isfinite(number):
        raise ValueError(f"{field} must be finite and within DOUBLE magnitude")
    # Explicit context makes the result independent of the caller's Decimal
    # precision/rounding. Float conversion uses Python's shortest decimal string.
    # Allow one more integer digit when rounding carries across a power of ten.
    context = Context(prec=max(28, number.adjusted() + 6), rounding=ROUND_HALF_EVEN)
    rounded = number.quantize(Decimal("0.0001"), context=context)
    return "0.0000" if rounded.is_zero() else format(rounded, ".4f")


def _canonical_parts(record: Mapping[str, object]) -> tuple[RecordKey, str]:
    if not isinstance(record, Mapping) or any(not isinstance(key, str) for key in record):
        raise ValueError("record must be a mapping with string keys")
    if set(record) != RECORD_FIELDS:
        missing, extra = sorted(RECORD_FIELDS - record.keys()), sorted(record.keys() - RECORD_FIELDS)
        raise ValueError(f"record fields do not match the payload schema; missing={missing}, extra={extra}")
    values = dict(record)
    for field in ("station_id", "reason"):
        if not isinstance(values[field], str) or not values[field].strip():
            raise ValueError(f"{field} must be a nonblank string")
    if not isinstance(values["label"], str) or values["label"] not in LABELS:
        raise ValueError("label must be one of the three Gold classification labels")
    if type(values["low_confidence"]) is not bool:
        raise ValueError("low_confidence must be a boolean from classification evidence")
    if type(values["neighbor_count"]) is not int or values["neighbor_count"] < 0:
        raise ValueError("neighbor_count must be a nonnegative integer")
    ts = _utc_timestamp(values["ts"])
    values["ts"] = ts
    encoded = []
    for field in sorted(RECORD_FIELDS):
        value = values[field]
        if field in FLOAT_FIELDS and (value is not None or field == "value"):
            token = _fixed_number(value, field)
        else:
            token = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        encoded.append(json.dumps(field) + ":" + token)
    canonical = "{" + ",".join(encoded) + "}"
    try:
        canonical.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("record strings must contain valid UTF-8 characters") from exc
    return (values["station_id"], ts), canonical


def canonical_record(record: Mapping[str, object]) -> str:
    """Return sorted, compact JSON with fixed four-decimal numeric fields.

    Pass exactly RECORD_FIELDS: Gold data columns plus low_confidence/reason
    from its evidence view, excluding record_hash and batch_id. No caller data
    is changed. Schema/type errors raise ValueError.
    """
    return _canonical_parts(record)[1]


def _leaf(canonical: str) -> bytes:
    return sha256(b"\x00" + canonical.encode("utf-8")).digest()


def hash_record(record: Mapping[str, object]) -> bytes:
    """Return the 32-byte domain-separated leaf; use .hex() for JSON/storage."""
    return _leaf(canonical_record(record))


def _parent(left: bytes, right: bytes) -> bytes:
    return sha256(b"\x01" + left + right).digest()


@dataclass(frozen=True)
class MerkleProof:
    """Zero-based sorted leaf index and (raw sibling hash, sibling side) path."""

    leaf_index: int
    path: tuple[tuple[bytes, Side], ...]


@dataclass(frozen=True, init=False)
class MerkleTree:
    """An immutable snapshot, sorted by (station_id, normalized UTC ts).

    Duplicate keys and empty input raise ValueError. Every odd level duplicates
    its final node, including intermediate levels. A single leaf is its root.
    """

    keys: tuple[RecordKey, ...]
    canonical_records: tuple[str, ...]
    _levels: tuple[tuple[bytes, ...], ...]

    def __init__(self, records: Iterable[Mapping[str, object]]) -> None:
        entries = sorted(_canonical_parts(record) for record in records)
        if not entries:
            raise ValueError("cannot build a Merkle tree with no records")
        keys = tuple(key for key, _ in entries)
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate (station_id, ts) keys are not allowed")
        canonical = tuple(value for _, value in entries)
        levels = [tuple(_leaf(value) for value in canonical)]
        while len(levels[-1]) > 1:
            level = levels[-1]
            levels.append(tuple(_parent(level[i], level[min(i + 1, len(level) - 1)])
                                for i in range(0, len(level), 2)))
        object.__setattr__(self, "keys", keys)
        object.__setattr__(self, "canonical_records", canonical)
        object.__setattr__(self, "_levels", tuple(levels))

    @property
    def root(self) -> bytes:
        return self._levels[-1][0]

    @property
    def leaf_hashes(self) -> tuple[bytes, ...]:
        return self._levels[0]

    @property
    def record_count(self) -> int:
        return len(self.keys)

    def proof(self, leaf_index: int) -> MerkleProof:
        """Build a bottom-up path for an index in canonical_records/keys."""
        if type(leaf_index) is not int or not 0 <= leaf_index < self.record_count:
            raise ValueError("leaf_index must identify a sorted leaf in this tree")
        index = leaf_index
        path: list[tuple[bytes, Side]] = []
        for level in self._levels[:-1]:
            sibling = index - 1 if index % 2 else min(index + 1, len(level) - 1)
            path.append((level[sibling], "left" if index % 2 else "right"))
            index //= 2
        return MerkleProof(leaf_index, tuple(path))


def _is_hash(value: object) -> bool:
    return isinstance(value, bytes) and len(value) == 32


def verify_proof(
    record: Mapping[str, object], proof: MerkleProof, root: bytes, *, record_count: int,
) -> bool:
    """Verify against a trusted root AND count; malformed input returns False.

    Root/count must come from the same trusted batch (the on-chain registry in
    task 8). A root alone cannot authenticate the count under odd duplication.
    This verifies inclusion at four-decimal precision, not sensor correctness.
    """
    if not _is_hash(root) or type(record_count) is not int or record_count < 1:
        return False
    if not isinstance(proof, MerkleProof) or type(proof.leaf_index) is not int:
        return False
    if not 0 <= proof.leaf_index < record_count or not isinstance(proof.path, tuple):
        return False
    try:
        digest = hash_record(record)
    except (ValueError, TypeError, OverflowError):
        return False
    index, width = proof.leaf_index, record_count
    for step in proof.path:
        if width == 1 or not isinstance(step, tuple) or len(step) != 2:
            return False
        sibling, side = step
        if not _is_hash(sibling) or side != ("left" if index % 2 else "right"):
            return False
        # Odd final nodes must prove the specified self-duplication, not an
        # arbitrary hidden extra leaf. The count is deliberately caller-trusted.
        if index == width - 1 and width % 2 and sibling != digest:
            return False
        digest = _parent(sibling, digest) if side == "left" else _parent(digest, sibling)
        index, width = index // 2, (width + 1) // 2
    return width == 1 and digest == root
