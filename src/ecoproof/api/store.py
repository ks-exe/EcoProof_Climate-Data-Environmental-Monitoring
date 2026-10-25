"""Short, read-only DuckDB snapshots. No API request creates or rebuilds data."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import json

import duckdb
from fastapi import HTTPException

from ecoproof.config import Settings
from ecoproof.provenance.batches import Batch, _load_batch


READING_SELECT = """SELECT c.*, e.low_confidence, e.reason, e.baseline_sigma, e.smoothed_z
    FROM gold.classified c LEFT JOIN gold.classification_evidence e USING (station_id, ts)"""
BATCH_SELECT = """SELECT b.*, s.contract_address FROM gold.batches b
    LEFT JOIN gold.anchor_submissions s USING (batch_id)"""


@contextmanager
def snapshot(settings: Settings) -> Iterator[duckdb.DuckDBPyConnection]:
    try:
        if not settings.duckdb_path.is_file():
            raise HTTPException(503, "Data database is missing; ingest observations and build Silver/Gold first")
        with duckdb.connect(str(settings.duckdb_path), read_only=True) as db:
            db.execute("BEGIN TRANSACTION")
            yield db
            db.execute("COMMIT")
    except (duckdb.Error, OSError):
        raise HTTPException(503, "Local data is unavailable; check completed builds and stop pipeline writers before serving") from None


def available(db: duckdb.DuckDBPyConnection, *tables: str) -> bool:
    names = {f"{schema}.{table}" for schema, table in db.execute(
        "SELECT table_schema, table_name FROM information_schema.tables"
    ).fetchall()}
    return set(tables) <= names


def require(db: duckdb.DuckDBPyConnection, *tables: str) -> None:
    if not available(db, *tables):
        raise HTTPException(503, "Required data views are missing; complete the Silver/Gold build and batch preparation")


def rows(db: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> list[dict]:
    result = db.execute(sql, params or [])
    names = [column[0] for column in result.description]
    return [{name: utc(value) for name, value in zip(names, values)} for values in result.fetchall()]


def utc(value: object) -> object:
    if isinstance(value, datetime):
        # DuckDB TIMESTAMP is naive by schema and always represents UTC here.
        return value.replace(tzinfo=timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    return value


def sql_time(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def stored_batch(db: duckdb.DuckDBPyConnection, batch_id: str) -> tuple[Batch, dict]:
    require(db, "gold.batches", "gold.batch_records", "gold.anchor_submissions")
    metadata = rows(db, BATCH_SELECT + " WHERE b.batch_id = ?", [batch_id])
    if not metadata:
        raise HTTPException(404, "Unknown batch_id")
    try:
        batch = _load_batch(db, batch_id)
    except (ValueError, TypeError, KeyError, OverflowError):
        raise HTTPException(409, "Saved batch snapshot is inconsistent; inspect its retained records") from None
    return batch, metadata[0]


def proof_payload(batch: Batch, metadata: dict, index: int) -> dict:
    if not 0 <= index < batch.tree.record_count:
        raise HTTPException(404, "No record at that batch leaf_index")
    canonical = batch.tree.canonical_records[index]
    return {"batch": metadata, "leaf_index": index,
            "record": json.loads(canonical, parse_float=Decimal), "canonical_record": canonical,
            "record_hash": batch.tree.leaf_hashes[index].hex(), "root": batch.tree.root.hex(),
            "path": [{"sibling_hash": sibling.hex(), "side": side}
                     for sibling, side in batch.tree.proof(index).path]}
