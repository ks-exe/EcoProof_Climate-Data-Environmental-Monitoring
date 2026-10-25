"""Read-only EcoProof HTTP API (spec section 8, excluding stretch chat)."""

from collections.abc import Callable
from datetime import timedelta, datetime, timezone
import json
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse

from ecoproof.api import store
from ecoproof.api.models import (BatchSummary, ErrorResponse, Event, EventLabel, Identifier,
                                ProofResponse, Reading, Station, UTCDateTime, VerifyRequest, VerifyResponse)
from ecoproof.api.requests import ExactJSONRoute
from ecoproof.config import Settings, load_settings
from ecoproof.provenance.anchor import Registry, SEPOLIA_CHAIN_ID, public_client, registry_address
from ecoproof.provenance.merkle import MerkleProof, hash_record, verify_proof


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_registry_factory(settings: Annotated[Settings, Depends(get_settings)]) -> Callable[[], Registry]:
    # Lazy: validate the uploaded record and local snapshot before contacting RPC.
    return lambda: Registry(public_client(settings), registry_address(settings), chain_id=SEPOLIA_CHAIN_ID)


SettingsDep = Annotated[Settings, Depends(get_settings)]
RegistryFactoryDep = Annotated[Callable[[], Registry], Depends(get_registry_factory)]


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="EcoProof API", version="0.1.0", description=(
        "Read-only classified air data and Merkle verification. A proof establishes canonical record "
        "integrity at anchoring time, not sensor correctness. Low-confidence VALID is not verified healthy."
    ), responses={code: {"model": ErrorResponse} for code in (404, 409, 413, 415, 422, 503)})
    app.state.settings = settings if settings is not None else load_settings()
    app.router.route_class = ExactJSONRoute

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Never echo uploaded bodies or arbitrary input values in error responses.
        return JSONResponse(status_code=422, content={"detail": "Invalid request; check the field types and constraints in /docs"})

    @app.exception_handler(ResponseValidationError)
    async def invalid_data(request: Request, exc: ResponseValidationError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": "Stored data does not satisfy the API schema; inspect the completed build"})

    @app.get("/stations", response_model=list[Station])
    def stations(settings: SettingsDep) -> list[dict]:
        """All station coordinates, with the most recent classification or null."""
        with store.snapshot(settings) as db:
            store.require(db, "silver.stations")
            result = store.rows(db, "SELECT * FROM silver.stations ORDER BY station_id")
            latest = {}
            if store.available(db, "gold.classified"):
                store.require(db, "gold.classification_evidence")
                latest = {row["station_id"]: row for row in store.rows(db, store.READING_SELECT +
                    " QUALIFY row_number() OVER (PARTITION BY c.station_id ORDER BY c.ts DESC) = 1")}
            return [{**station, "latest": latest.get(station["station_id"])} for station in result]

    @app.get("/readings", response_model=list[Reading])
    def readings(settings: SettingsDep, station: Identifier,
                 start: Annotated[UTCDateTime, Query(alias="from")],
                 end: Annotated[UTCDateTime, Query(alias="to")]) -> list[dict]:
        """Classified hourly observations in [from, to), ascending; at most 31 days."""
        if not start < end or end - start > timedelta(days=31):
            raise HTTPException(422, "Require from < to and a window of at most 31 days")
        with store.snapshot(settings) as db:
            store.require(db, "gold.classified", "gold.classification_evidence")
            return store.rows(db, store.READING_SELECT +
                " WHERE c.station_id = ? AND c.ts >= ? AND c.ts < ? ORDER BY c.ts",
                [station, store.sql_time(start), store.sql_time(end)])

    @app.get("/events", response_model=list[Event])
    def events(settings: SettingsDep, label: EventLabel | None = None,
               limit: Annotated[int, Query(ge=1, le=1000)] = 100) -> list[dict]:
        """Recent suspected faults/plumes with saved wind and downwind evidence."""
        with store.snapshot(settings) as db:
            store.require(db, "gold.classified", "gold.classification_evidence")
            result = store.rows(db, """SELECT c.*, e.low_confidence, e.reason, e.baseline_sigma, e.smoothed_z,
                e.plume_evidence_json, e.plume_sources_json FROM gold.classified c
                LEFT JOIN gold.classification_evidence e USING (station_id, ts)
                WHERE c.label <> 'VALID' AND (? IS NULL OR c.label = ?)
                ORDER BY c.ts DESC, c.station_id LIMIT ?""", [label, label, limit])
            try:
                for row in result:
                    row["plume_evidence"] = json.loads(row.pop("plume_evidence_json"))
                    row["plume_sources"] = json.loads(row.pop("plume_sources_json"))
            except (ValueError, TypeError):
                raise HTTPException(503, "Stored event evidence is invalid; inspect the completed Gold build") from None
            return result

    @app.get("/batches", response_model=list[BatchSummary])
    def batches(settings: SettingsDep, limit: Annotated[int, Query(ge=1, le=1000)] = 100,
                offset: Annotated[int, Query(ge=0, le=100000)] = 0) -> list[dict]:
        """Saved batch metadata, newest window first; null chain fields mean unmined."""
        with store.snapshot(settings) as db:
            store.require(db, "gold.batches", "gold.anchor_submissions")
            return store.rows(db, store.BATCH_SELECT +
                              " ORDER BY b.window_start DESC, b.batch_id LIMIT ? OFFSET ?", [limit, offset])

    @app.get("/proof", response_model=ProofResponse)
    def proof(settings: SettingsDep, station: Identifier, ts: UTCDateTime,
              batch_id: Identifier | None = None) -> dict:
        """Current matching Gold proof, or an explicit retained batch after a rebuild."""
        with store.snapshot(settings) as db:
            if batch_id is None:
                store.require(db, "gold.classified")
                link = db.execute("SELECT batch_id FROM gold.classified WHERE station_id = ? AND ts = ?",
                                  [station, store.sql_time(ts)]).fetchone()
                if not link or not link[0]:
                    raise HTTPException(404, "No prepared batch matches that current Gold record")
                batch_id = link[0]
            batch, metadata = store.stored_batch(db, batch_id)
            key = (station, store.utc(store.sql_time(ts)))
            if key not in batch.tree.keys:
                raise HTTPException(404, "Record is not in the selected batch")
            return store.proof_payload(batch, metadata, batch.tree.keys.index(key))

    @app.post("/verify", response_model=VerifyResponse)
    def verify(upload: VerifyRequest, settings: SettingsDep, factory: RegistryFactoryDep) -> dict:
        """Hash the uploaded record; check a rebuilt/optional supplied path against live chain state."""
        with store.snapshot(settings) as db:
            batch, metadata = store.stored_batch(db, upload.batch_id)
            if not 0 <= upload.leaf_index < batch.tree.record_count:
                raise HTTPException(404, "No record at that batch leaf_index")
        proof = batch.tree.proof(upload.leaf_index)
        if upload.path is not None:
            proof = MerkleProof(upload.leaf_index, tuple((bytes.fromhex(step.sibling_hash), step.side) for step in upload.path))
        try:
            registry = factory()
            if ((metadata["chain_id"] is not None and metadata["chain_id"] != registry.chain_id)
                    or (metadata["contract_address"] is not None
                        and metadata["contract_address"].lower() != registry.address.lower())):
                raise HTTPException(409, "Batch was submitted to a different chain or registry than the server configuration")
            on_chain = registry.read(batch.batch_id)
        except HTTPException:
            raise
        except Exception:
            # Provider exceptions can contain authenticated RPC URLs. Do not echo them.
            raise HTTPException(503, "Chain verification unavailable; check Sepolia RPC, registry configuration and compiled contract") from None
        payload = upload.record.payload()
        if not on_chain["anchored_at"]:
            code, reason = "unanchored", "No anchor exists for this batch in the configured registry"
        elif not registry.matches(batch, on_chain):
            code, reason = "batch_mismatch", "Saved batch root, window or count differs from the on-chain batch"
        elif not verify_proof(payload, proof, on_chain["root"], record_count=on_chain["record_count"]):
            code, reason = "record_mismatch", "Uploaded canonical record or Merkle path does not match the on-chain batch"
        else:
            code, reason = "verified", "Canonical record and Merkle path match the on-chain batch; this does not prove sensor correctness"
        return {"verified": code == "verified", "code": code, "reason": reason,
                "batch_id": batch.batch_id, "leaf_index": upload.leaf_index,
                "record_hash": hash_record(payload).hex(), "on_chain_root": on_chain["root"].hex() if on_chain["anchored_at"] else None,
                "record_count": on_chain["record_count"], "chain_id": registry.chain_id,
                "contract_address": registry.address, "tx_hash": metadata["tx_hash"],
                "anchored_at": datetime.fromtimestamp(on_chain["anchored_at"], timezone.utc) if on_chain["anchored_at"] else None}

    return app


app = create_app()
