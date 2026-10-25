"""Hourly confident-VALID batches and immutable canonical snapshots in DuckDB."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path

import duckdb

from ecoproof.config import Settings
from ecoproof.detect.classifier import utc_hour
from ecoproof.provenance.merkle import MerkleTree, RECORD_FIELDS, hash_record


@dataclass(frozen=True)
class Batch:
    batch_id: str
    window_start: datetime
    window_end: datetime
    tree: MerkleTree


def ensure_tables(db: duckdb.DuckDBPyConnection) -> None:
    db.execute("""
        CREATE SCHEMA IF NOT EXISTS gold;
        CREATE TABLE IF NOT EXISTS gold.batches (
            batch_id TEXT PRIMARY KEY, window_start TIMESTAMP NOT NULL,
            window_end TIMESTAMP NOT NULL, record_count INTEGER NOT NULL CHECK (record_count > 0),
            merkle_root TEXT NOT NULL, tx_hash TEXT, chain_id INTEGER, anchored_at TIMESTAMP);
        CREATE TABLE IF NOT EXISTS gold.batch_records (
            batch_id TEXT NOT NULL, leaf_index INTEGER NOT NULL, station_id TEXT NOT NULL,
            ts TIMESTAMP NOT NULL, canonical_record TEXT NOT NULL, record_hash TEXT NOT NULL,
            PRIMARY KEY (batch_id, leaf_index), UNIQUE (batch_id, station_id, ts));
        CREATE TABLE IF NOT EXISTS gold.anchor_submissions (
            batch_id TEXT PRIMARY KEY, chain_id INTEGER NOT NULL, contract_address TEXT NOT NULL,
            tx_hash TEXT NOT NULL, raw_transaction BLOB NOT NULL);
    """)


def publish_classified_view(db: duckdb.DuckDBPyConnection, path: Path) -> None:
    """Choose one matching batch per record, preferring mined batches.

    Rebuilt records only inherit a batch link when their committed hash matches.
    A record can legitimately occur in multiple batch revisions; never duplicate
    Gold rows when joining the immutable history.
    """
    ensure_tables(db)
    source = str(path.resolve()).replace("'", "''")
    db.execute(f"""
        CREATE OR REPLACE VIEW gold.classified AS
        SELECT c.* REPLACE (links.batch_id AS batch_id)
        FROM read_parquet('{source}') c LEFT JOIN (
            SELECT r.station_id, r.ts, r.record_hash, r.batch_id
            FROM gold.batch_records r JOIN gold.batches b USING (batch_id)
            QUALIFY row_number() OVER (
                PARTITION BY r.station_id, r.ts, r.record_hash
                ORDER BY (b.tx_hash IS NOT NULL) DESC, b.anchored_at DESC NULLS LAST, r.batch_id
            ) = 1
        ) links USING (station_id, ts, record_hash)
    """)


def classification_payload(record: object) -> dict[str, object]:
    """Project a classifier dataclass without derived metadata or extra evidence."""
    return {name: getattr(record, name) for name in RECORD_FIELDS}


def _load_batch(db: duckdb.DuckDBPyConnection, batch_id: str) -> Batch:
    row = db.execute("""SELECT window_start, window_end, record_count, merkle_root
                        FROM gold.batches WHERE batch_id = ?""", [batch_id]).fetchone()
    if row is None:
        raise ValueError("Unknown batch_id; prepare a batch first")
    stored = db.execute("""SELECT leaf_index, station_id, ts, canonical_record, record_hash
                           FROM gold.batch_records WHERE batch_id = ? ORDER BY leaf_index""", [batch_id]).fetchall()
    tree = MerkleTree(json.loads(item[3], parse_float=Decimal) for item in stored)
    if tree.record_count != row[2] or tree.root.hex() != row[3]:
        raise ValueError("Stored batch snapshot does not match its root/count")
    for index, (position, station, ts, canonical, leaf) in enumerate(stored):
        key = (station, ts.replace(tzinfo=timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"))
        if (position != index or canonical != tree.canonical_records[index]
                or key != tree.keys[index] or leaf != tree.leaf_hashes[index].hex()):
            raise ValueError("Stored batch records have inconsistent indices, keys, or hashes")
    start, end = (item.replace(tzinfo=timezone.utc) for item in row[:2])
    if end - start != timedelta(hours=1) or utc_hour(start) != start:
        raise ValueError("Stored batch has an invalid hourly window")
    for canonical in tree.canonical_records:
        payload = json.loads(canonical)
        ts = datetime.fromisoformat(payload["ts"])
        if not start <= ts < end or payload["label"] != "VALID" or payload["low_confidence"]:
            raise ValueError("Stored validated batch contains an ineligible record")
    expected_id = f"ecoproof:v1:valid:{start.strftime('%Y%m%dT%H%M%SZ')}:{tree.root.hex()}"
    if batch_id != expected_id:
        raise ValueError("Stored batch identifier does not match its window/root")
    return Batch(batch_id, start, end, tree)


def load_batch(database: Path, batch_id: str) -> Batch:
    with duckdb.connect(str(database), read_only=True) as db:
        return _load_batch(db, batch_id)


def prepare_batches(settings: Settings, *, start: datetime, end: datetime) -> list[Batch]:
    """Snapshot observed hourly records, with no filling and no chain writes.

    One transaction publishes the selected window. Empty hours are skipped.
    Existing identical batches are verified and reused, never overwritten.
    """
    start, end = utc_hour(start), utc_hour(end)
    if start >= end:
        raise ValueError("Require start < end")
    if not settings.duckdb_path.is_file():
        raise ValueError("No Gold database; ingest air observations and run make detect first")
    with duckdb.connect(str(settings.duckdb_path)) as db:
        if db.execute("""SELECT count(*) FROM information_schema.tables WHERE table_schema='gold'
                          AND table_name IN ('classified','classification_evidence')""").fetchone()[0] != 2:
            raise ValueError("Gold classifications/evidence are missing; run make detect after ingesting air observations")
        db.execute("BEGIN TRANSACTION")
        try:
            ensure_tables(db)
            result = db.execute("""
                SELECT c.station_id, c.ts, c.value, c.expected, c.residual, c.z, c.label,
                       c.neighbor_count, c.wind_speed, c.wind_dir_deg, e.low_confidence, e.reason,
                       c.record_hash
                FROM gold.classified c LEFT JOIN gold.classification_evidence e USING (station_id, ts)
                WHERE c.ts >= ? AND c.ts < ? ORDER BY c.ts, c.station_id
            """, [start.replace(tzinfo=None), end.replace(tzinfo=None)])
            names = [item[0] for item in result.description]
            groups: dict[datetime, list[dict[str, object]]] = {}
            for values in result.fetchall():
                payload = dict(zip(names, values))
                stored_hash = payload.pop("record_hash")
                if type(payload["low_confidence"]) is not bool or not payload["reason"]:
                    raise ValueError("Gold confidence evidence is missing; rebuild Gold before batching")
                if payload["label"] != "VALID" or payload["low_confidence"]:
                    continue
                ts = payload["ts"]
                if not isinstance(ts, datetime) or ts.tzinfo is not None:
                    raise ValueError("Gold TIMESTAMP must use its documented naive UTC representation")
                payload["ts"] = utc_hour(ts.replace(tzinfo=timezone.utc))
                if hash_record(payload).hex() != stored_hash:
                    raise ValueError("Gold record_hash is absent or inconsistent; rebuild Gold with make detect")
                groups.setdefault(payload["ts"], []).append(payload)
            prepared = []
            for hour, records in sorted(groups.items()):
                tree = MerkleTree(records)
                batch_id = f"ecoproof:v1:valid:{hour.strftime('%Y%m%dT%H%M%SZ')}:{tree.root.hex()}"
                exists = db.execute("SELECT 1 FROM gold.batches WHERE batch_id = ?", [batch_id]).fetchone()
                if not exists:
                    db.execute("INSERT INTO gold.batches VALUES (?,?,?,?,?,NULL,NULL,NULL)",
                               [batch_id, hour.replace(tzinfo=None), (hour + timedelta(hours=1)).replace(tzinfo=None),
                                tree.record_count, tree.root.hex()])
                    db.executemany("INSERT INTO gold.batch_records VALUES (?,?,?,?,?,?)", [
                        (batch_id, index, key[0], datetime.fromisoformat(key[1]).replace(tzinfo=None),
                         canonical, tree.leaf_hashes[index].hex())
                        for index, (key, canonical) in enumerate(zip(tree.keys, tree.canonical_records))
                    ])
                prepared.append(_load_batch(db, batch_id))
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
    return prepared
