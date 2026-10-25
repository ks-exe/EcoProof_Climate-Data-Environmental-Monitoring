"""Gold rebuilds must preserve canonical batch history and confidence semantics."""

from dataclasses import replace
from datetime import timedelta
import json

import duckdb
import pytest

from ecoproof.config import Settings
from ecoproof.provenance.batches import load_batch, prepare_batches
from ecoproof.provenance.merkle import verify_proof


def query(settings, sql, parameters=None):
    with duckdb.connect(str(settings.duckdb_path), read_only=True) as db:
        return db.execute(sql, parameters or []).fetchall()


def test_hourly_selection_boundaries_and_live_gold_links(gold_snapshot):
    settings, start, records, _ = gold_snapshot
    batches = prepare_batches(settings, start=start, end=start + timedelta(hours=3))
    assert [item.tree.record_count for item in batches] == [3, 1]
    assert [item.window_start for item in batches] == [start, start + timedelta(hours=1)]
    assert all(item.window_end - item.window_start == timedelta(hours=1) for item in batches)
    assert query(settings, "SELECT count(*) FROM gold.classified") == [(len(records),)]
    linked = query(settings, "SELECT station_id FROM gold.classified WHERE batch_id IS NOT NULL ORDER BY ts,station_id")
    assert linked == [("a",), ("b",), ("c",), ("a",)]
    assert query(settings, "SELECT count(tx_hash), count(chain_id), count(anchored_at) FROM gold.batches") == [(0, 0, 0)]
    assert prepare_batches(settings, start=start + timedelta(hours=2), end=start + timedelta(hours=3)) == []


def test_reordered_rebuild_is_idempotent_and_inputs_remain_unchanged(gold_snapshot):
    settings, start, records, publish = gold_snapshot
    before = {path: path.read_bytes() for path in settings.gold_dir.rglob("*.parquet")}
    first = prepare_batches(settings, start=start, end=start + timedelta(hours=2))
    assert {path: path.read_bytes() for path in before} == before
    publish(reversed(records))
    again = prepare_batches(settings, start=start, end=start + timedelta(hours=2))
    assert first == again
    assert query(settings, "SELECT count(*) FROM gold.batches") == [(2,)]
    assert query(settings, "SELECT count(*) FROM gold.batch_records") == [(4,)]


def test_changed_gold_gets_new_root_without_breaking_old_proofs(gold_snapshot):
    settings, start, records, publish = gold_snapshot
    old = prepare_batches(settings, start=start, end=start + timedelta(hours=1))[0]
    publish([replace(row, value=20) if row.station_id == "b" else row for row in records])
    assert query(settings, "SELECT batch_id FROM gold.classified WHERE station_id='b'") == [(None,)]
    new = prepare_batches(settings, start=start, end=start + timedelta(hours=1))[0]
    assert old.batch_id != new.batch_id and old.tree.root != new.tree.root
    assert load_batch(settings.duckdb_path, old.batch_id) == old
    payload = json.loads(old.tree.canonical_records[1])
    assert payload["value"] == 12.5
    assert verify_proof(payload, old.tree.proof(1), old.tree.root, record_count=3)
    assert query(settings, "SELECT count(*) FROM gold.classified") == [(len(records),)]
    assert query(settings, "SELECT batch_id FROM gold.classified WHERE station_id='b'") == [(new.batch_id,)]


@pytest.mark.parametrize("problem", ["missing_evidence", "null_hash", "wrong_hash"])
def test_bad_gold_rolls_back_every_batch_in_window(gold_snapshot, problem):
    settings, start, _, _ = gold_snapshot
    with duckdb.connect(str(settings.duckdb_path)) as db:
        if problem == "missing_evidence":
            db.execute("CREATE TABLE replacement AS SELECT * FROM gold.classification_evidence WHERE ts < TIMESTAMP '2026-10-21 01:00:00'")
            db.execute("CREATE OR REPLACE VIEW gold.classification_evidence AS SELECT * FROM replacement")
        else:
            db.execute("CREATE TABLE replacement AS SELECT * FROM gold.classified")
            db.execute("UPDATE replacement SET record_hash=? WHERE ts=TIMESTAMP '2026-10-21 01:00:00'",
                       [None if problem == "null_hash" else "f" * 64])
            db.execute("CREATE OR REPLACE VIEW gold.classified AS SELECT * FROM replacement")
    with pytest.raises(ValueError):
        prepare_batches(settings, start=start, end=start + timedelta(hours=2))
    assert query(settings, "SELECT count(*) FROM gold.batches") == [(0,)]
    assert query(settings, "SELECT count(*) FROM gold.batch_records") == [(0,)]


def test_corrupt_snapshot_is_rejected_instead_of_silently_replaced(gold_snapshot):
    settings, start, _, _ = gold_snapshot
    batch = prepare_batches(settings, start=start, end=start + timedelta(hours=1))[0]
    with duckdb.connect(str(settings.duckdb_path)) as db:
        db.execute("UPDATE gold.batch_records SET record_hash=? WHERE batch_id=? AND leaf_index=0", ["0" * 64, batch.batch_id])
    with pytest.raises(ValueError, match="inconsistent"):
        load_batch(settings.duckdb_path, batch.batch_id)
    with pytest.raises(ValueError):
        prepare_batches(settings, start=start, end=start + timedelta(hours=1))


def test_missing_database_and_empty_or_naive_windows_fail(tmp_path, gold_snapshot):
    settings, start, _, _ = gold_snapshot
    missing = Settings(tmp_path / "missing")
    with pytest.raises(ValueError, match="No Gold database"):
        prepare_batches(missing, start=start, end=start + timedelta(hours=1))
    assert not missing.data_dir.exists()
    for begin, end in ((start, start), (start.replace(tzinfo=None), start + timedelta(hours=1))):
        with pytest.raises(ValueError):
            prepare_batches(settings, start=begin, end=end)


def test_low_confidence_rebuild_cannot_inherit_validated_batch_link(gold_snapshot):
    settings, start, records, publish = gold_snapshot
    batch = prepare_batches(settings, start=start, end=start + timedelta(hours=1))[0]
    publish([replace(row, low_confidence=True) if row.station_id == "a" else row for row in records])
    assert query(settings, "SELECT count(batch_id) FROM gold.classified WHERE station_id='a'") == [(0,)]
    assert load_batch(settings.duckdb_path, batch.batch_id) == batch
