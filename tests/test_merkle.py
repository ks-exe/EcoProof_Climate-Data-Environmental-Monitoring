"""Synthetic payloads only: canonical byte contract and adversarial proofs."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_UP, localcontext
from hashlib import sha256
import json
from itertools import permutations

import pytest

from ecoproof.provenance.merkle import (
    MerkleProof, MerkleTree, canonical_record, hash_record, verify_proof,
)


def record(station: str = "synthetic-a", **changes: object) -> dict[str, object]:
    return {
        "station_id": station, "ts": "2026-10-21T00:00:00Z", "value": 12.5,
        "expected": 12, "residual": 0.5, "z": 0.25, "label": "VALID",
        "neighbor_count": 2, "wind_speed": 2, "wind_dir_deg": 270,
        "low_confidence": False, "reason": "synthetic fixture", **changes,
    }


def test_exact_canonical_utf8_preimage_and_domain_separation() -> None:
    payload = record("synthetic-é", ts="2026-10-21T05:00:00+05:00", value=12.34565,
                     residual=-0.00001, z=Decimal("1.23455"), reason='synthetic "fixture"\nonly')
    expected = (
        '{"expected":12.0000,"label":"VALID","low_confidence":false,"neighbor_count":2,'
        '"reason":"synthetic \\"fixture\\"\\nonly","residual":0.0000,"station_id":"synthetic-é",'
        '"ts":"2026-10-21T00:00:00.000000Z","value":12.3456,"wind_dir_deg":270.0000,'
        '"wind_speed":2.0000,"z":1.2346}'
    )
    assert canonical_record(payload) == expected
    assert json.loads(expected)["reason"] == 'synthetic "fixture"\nonly'
    assert hash_record(payload) == sha256(b"\x00" + expected.encode("utf-8")).digest()
    assert hash_record(payload) != sha256(expected.encode("utf-8")).digest()


@pytest.mark.parametrize("number,expected", [
    (12, "12.0000"), (12.0, "12.0000"), (Decimal("12.00000"), "12.0000"),
    (1.23445, "1.2344"), (1.23455, "1.2346"), (-1.23445, "-1.2344"),
    (9.99995, "10.0000"), (-0.0, "0.0000"), (1e-300, "0.0000"),
])
def test_fixed_numeric_rounding_independent_of_decimal_context(number: object, expected: str) -> None:
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_UP
        canonical = canonical_record(record(value=number))
    assert f'"value":{expected},' in canonical


def test_large_finite_double_is_supported_without_scientific_notation() -> None:
    canonical = canonical_record(record(residual=1e308))
    assert '"residual":1' + '0' * 308 + '.0000,' in canonical


@pytest.mark.parametrize("sign", ["", "-"])
def test_decimal_rounding_carry_and_exact_json_round_trip(sign: str) -> None:
    payload = record(residual=Decimal(sign + "9" * 40 + ".99995"))
    canonical = canonical_record(payload)
    assert '"residual":' + sign + '1' + '0' * 40 + '.0000,' in canonical
    decoded = json.loads(canonical, parse_float=Decimal)
    assert canonical_record(decoded) == canonical
    assert hash_record(decoded) == hash_record(payload)


def test_same_numeric_value_and_timezone_have_identical_hashes() -> None:
    payload = record(ts="2026-10-21T05:00:00+05:00", value=12, wind_speed=2.0)
    timestamp = datetime(2026, 10, 20, 20, tzinfo=timezone(timedelta(hours=-4)))
    equivalent = record(ts=timestamp, value=Decimal("12.0000"), wind_speed=2)
    assert hash_record(payload) == hash_record(equivalent)
    assert canonical_record(payload) == canonical_record(dict(reversed(list(equivalent.items()))))


def test_fractional_seconds_are_preserved_and_null_is_distinct_from_zero() -> None:
    first = record(ts="2026-10-21T00:00:00.1Z", expected=None)
    assert '"ts":"2026-10-21T00:00:00.100000Z"' in canonical_record(first)
    assert '"expected":null' in canonical_record(first)
    assert hash_record(first) != hash_record({**first, "expected": 0})
    assert hash_record(first) != hash_record({**first, "ts": "2026-10-21T00:00:00.100001Z"})


@pytest.mark.parametrize("timestamp", [
    "2026-10-21", "2026-10-21T00:00:00", "2026-10-21T00:00:00.1234567Z",
    "2026-10-21T00:00:00+01:90", "2026-02-30T00:00:00Z",
    "2026-10-21T00:00:60Z", datetime(2026, 10, 21), 1792540800,
])
def test_rejects_ambiguous_or_invalid_timestamps(timestamp: object) -> None:
    with pytest.raises(ValueError):
        canonical_record(record(ts=timestamp))


@pytest.mark.parametrize("changes", [
    {"value": float("nan")}, {"z": float("inf")}, {"wind_speed": float("-inf")},
    {"residual": Decimal("sNaN")}, {"value": Decimal("1e309")},
    {"value": True}, {"value": None}, {"value": "12.5"}, {"expected": []},
    {"station_id": 3}, {"station_id": " "}, {"station_id": "\ud800"},
    {"label": "HEALTHY"}, {"label": []}, {"low_confidence": 0},
    {"neighbor_count": True}, {"neighbor_count": -1}, {"neighbor_count": 2.0},
    {"reason": None}, {"reason": ""}, {"record_hash": "ignored?"}, {"batch_id": "batch"},
])
def test_invalid_payloads_are_rejected_and_do_not_verify(changes: dict) -> None:
    valid = record()
    tree = MerkleTree([valid])
    invalid = {**valid, **changes}
    with pytest.raises(ValueError):
        canonical_record(invalid)
    assert not verify_proof(invalid, tree.proof(0), tree.root, record_count=1)


def test_rejects_missing_evidence_and_non_mapping_input() -> None:
    missing = record()
    del missing["low_confidence"]
    for invalid in (missing, None, [], {1: "wrong key"}):
        with pytest.raises(ValueError):
            canonical_record(invalid)


def parent(left: bytes, right: bytes) -> bytes:
    # Reference uses raw digests, not their hex encodings.
    return sha256(b"\x01" + left + right).digest()


def test_three_leaf_root_and_each_exact_path() -> None:
    records = [record(station) for station in ("a", "b", "c")]
    a, b, c = [hash_record(item) for item in records]
    ab, cc = parent(a, b), parent(c, c)
    tree = MerkleTree(records)
    assert tree.root == parent(ab, cc)
    assert tree.leaf_hashes == (a, b, c)
    assert tree.record_count == 3
    assert tree.proof(0) == MerkleProof(0, ((b, "right"), (cc, "right")))
    assert tree.proof(1) == MerkleProof(1, ((a, "left"), (cc, "right")))
    assert tree.proof(2) == MerkleProof(2, ((c, "right"), (ab, "left")))
    assert tree.root != sha256(ab + cc).digest()
    assert tree.root != sha256(b"\x01" + ab.hex().encode() + cc.hex().encode()).digest()


def test_odd_intermediate_level_duplicates_its_last_node() -> None:
    records = [record(str(i)) for i in range(6)]
    a, b, c, d, e, f = [hash_record(item) for item in records]
    ab, cd, ef = parent(a, b), parent(c, d), parent(e, f)
    tree = MerkleTree(records)
    assert tree.root == parent(parent(ab, cd), parent(ef, ef))
    assert tree.proof(5).path == ((e, "left"), (ef, "right"), (parent(ab, cd), "left"))


@pytest.mark.parametrize("count", [1, 2, 3, 5, 6, 7, 8, 9, 17])
def test_all_paths_verify_after_json_record_round_trip(count: int) -> None:
    tree = MerkleTree(record(f"station-{i:02d}") for i in range(count))
    for index, canonical in enumerate(tree.canonical_records):
        assert verify_proof(json.loads(canonical), tree.proof(index), tree.root, record_count=count)
    if count == 1:
        assert tree.root == tree.leaf_hashes[0]
        assert tree.proof(0).path == ()


def test_reordering_keeps_root_keys_records_and_proofs_identical() -> None:
    records = [record("2"), record("10", ts="2026-10-21T02:00:00Z"),
               record("10", ts="2026-10-21T06:00:00+05:00")]
    tree = MerkleTree(records)
    assert tree.keys == (("10", "2026-10-21T01:00:00.000000Z"),
                         ("10", "2026-10-21T02:00:00.000000Z"),
                         ("2", "2026-10-21T00:00:00.000000Z"))
    for order in permutations(records):
        reordered = MerkleTree(dict(reversed(list(item.items()))) for item in order)
        assert reordered == tree
        assert [reordered.proof(i) for i in range(3)] == [tree.proof(i) for i in range(3)]


def test_tree_does_not_change_inputs_or_retain_mutable_records() -> None:
    payload = record(ts=datetime(2026, 10, 21, tzinfo=timezone.utc))
    original = payload.copy()
    tree = MerkleTree([payload])
    before = tree.root
    assert payload == original
    payload["value"] = 100
    exported = json.loads(tree.canonical_records[0])
    exported["value"] = 200
    assert tree.root == before == hash_record(original)
    assert verify_proof(original, tree.proof(0), tree.root, record_count=1)
    with pytest.raises(FrozenInstanceError):
        tree.keys = ()


def test_empty_and_duplicate_keys_rejected_after_utc_normalization() -> None:
    with pytest.raises(ValueError, match="no records"):
        MerkleTree([])
    for duplicate in (record(), record(ts="2026-10-21T05:00:00+05:00", value=25)):
        with pytest.raises(ValueError, match="duplicate"):
            MerkleTree([record(), duplicate])


@pytest.mark.parametrize("index", [-1, 3, True, 1.0, "0"])
def test_invalid_proof_index_rejected(index: object) -> None:
    with pytest.raises(ValueError):
        MerkleTree([record("a"), record("b"), record("c")]).proof(index)


@pytest.mark.parametrize("field,value", [
    ("station_id", "changed"), ("ts", "2026-10-21T00:00:00.000001Z"),
    ("value", 12.5001), ("expected", 12.0001), ("residual", 0.5001), ("z", 0.2501),
    ("label", "SENSOR_FAULT_DRIFT"), ("neighbor_count", 3), ("wind_speed", 2.0001),
    ("wind_dir_deg", 270.0001), ("low_confidence", True), ("reason", "changed"),
])
def test_changing_each_committed_field_fails(field: str, value: object) -> None:
    payload = record("b")
    tree = MerkleTree([record("a"), payload, record("c")])
    assert not verify_proof({**payload, field: value}, tree.proof(1), tree.root, record_count=3)


def test_subprecision_changes_are_intentionally_not_detectable() -> None:
    payload = record()
    tree = MerkleTree([payload])
    assert verify_proof({**payload, "value": 12.50001}, tree.proof(0), tree.root, record_count=1)
    assert not verify_proof({**payload, "value": 12.5001}, tree.proof(0), tree.root, record_count=1)


def test_tampered_path_side_order_index_root_and_count_fail() -> None:
    payload = record("b")
    tree = MerkleTree([record("a"), payload, record("c"), record("d"), record("e")])
    proof = tree.proof(1)
    sibling, side = proof.path[0]
    modified_hash = bytes([sibling[0] ^ 1]) + sibling[1:]
    invalid_proofs = [
        replace(proof, path=((modified_hash, side),) + proof.path[1:]),
        replace(proof, path=((sibling, "right"),) + proof.path[1:]),
        replace(proof, path=tuple(reversed(proof.path))),
        replace(proof, path=proof.path[:-1]),
        replace(proof, path=proof.path + ((sibling, "right"),)),
        replace(proof, leaf_index=0), replace(proof, leaf_index=3),
    ]
    for invalid in invalid_proofs:
        assert not verify_proof(payload, invalid, tree.root, record_count=5)
    assert not verify_proof(payload, proof, b"\x00" * 32, record_count=5)
    assert not verify_proof(payload, proof, tree.root, record_count=2)
    assert not verify_proof(record("a"), proof, tree.root, record_count=5)


def test_odd_duplication_requires_trusted_count_and_actual_self_sibling() -> None:
    payload = record("c")
    tree = MerkleTree([record("a"), record("b"), payload])
    proof = tree.proof(2)
    # Padding would also be a fourth leaf if the caller trusted a count of four.
    padding_proof = MerkleProof(3, ((hash_record(payload), "left"), proof.path[1]))
    assert verify_proof(payload, padding_proof, tree.root, record_count=4)
    assert not verify_proof(payload, padding_proof, tree.root, record_count=3)
    # A supplied root/path could otherwise hide an arbitrary fourth leaf.
    extra = hash_record(record("hidden"))
    fake_root = parent(proof.path[1][0], parent(hash_record(payload), extra))
    fake_path = MerkleProof(2, ((extra, "right"), proof.path[1]))
    assert not verify_proof(payload, fake_path, fake_root, record_count=3)


def test_malformed_proofs_and_metadata_return_false() -> None:
    payload = record()
    tree = MerkleTree([payload])
    invalid_proofs = [None, (), MerkleProof(-1, ()), MerkleProof(True, ()),
                      MerkleProof(1, ()), MerkleProof(0, []), MerkleProof(0, ((b"", "right"),))]
    for invalid in invalid_proofs:
        assert not verify_proof(payload, invalid, tree.root, record_count=1)
    for root in (None, "00" * 32, b"", b"0" * 31, b"0" * 33, bytearray(tree.root)):
        assert not verify_proof(payload, tree.proof(0), root, record_count=1)
    for count in (0, -1, True, 1.0, "1", None):
        assert not verify_proof(payload, tree.proof(0), tree.root, record_count=count)
    two = MerkleTree([record("a"), record("b")])
    for step in ((), (b"",), (b"x" * 31, "right"), (b"x" * 33, "right"),
                 ("00" * 32, "right"), (two.leaf_hashes[1], "up"), None):
        assert not verify_proof(record("a"), MerkleProof(0, (step,)), two.root, record_count=2)


def test_classification_labels_and_confidence_are_committed_without_silent_filtering() -> None:
    payloads = [record("a"), record("b", label="VERIFIED_PLUME_EVENT"),
                record("c", label="SENSOR_FAULT_DRIFT"),
                record("d", low_confidence=True, reason="missing weather")]
    tree = MerkleTree(payloads)
    assert tree.record_count == 4
    for index, payload in enumerate(payloads):
        assert verify_proof(payload, tree.proof(index), tree.root, record_count=4)
