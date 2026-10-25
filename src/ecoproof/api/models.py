"""Public API schemas; verification retains JSON numbers until canonical hashing."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer, WithJsonSchema, model_validator

from ecoproof.provenance.merkle import RECORD_FIELDS, _utc_timestamp, canonical_record


Label = Literal["VALID", "SENSOR_FAULT_DRIFT", "VERIFIED_PLUME_EVENT"]
EventLabel = Literal["SENSOR_FAULT_DRIFT", "VERIFIED_PLUME_EVENT"]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(min_length=1, max_length=256)]
UTCDateTime = Annotated[datetime, BeforeValidator(lambda value: datetime.fromisoformat(_utc_timestamp(value)))]
# Decimal's default JSON serialization is a string. Responses use JSON numbers;
# canonical_record remains the authoritative, exact four-decimal representation.
Number = Annotated[int | float | Decimal, PlainSerializer(float, return_type=float, when_used="json"),
                   WithJsonSchema({"type": "number"})]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Record(Model):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    station_id: str
    ts: str = Field(json_schema_extra={"format": "date-time"})
    value: Number
    expected: Number | None
    residual: Number | None
    z: Number | None
    label: Label
    neighbor_count: int = Field(ge=0)
    wind_speed: Number | None
    wind_dir_deg: Number | None
    low_confidence: bool
    reason: str

    @model_validator(mode="before")
    @classmethod
    def check_payload(cls, value: object) -> object:
        # Validate the original values BEFORE Pydantic can turn bool into a float
        # or round a Decimal at a four-decimal half-even boundary.
        if isinstance(value, dict):
            canonical_record({key: item for key, item in value.items() if key in RECORD_FIELDS})
        return value

    def payload(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in RECORD_FIELDS}


class Reading(Record):
    record_hash: Hash
    batch_id: str | None
    baseline_sigma: float | None
    smoothed_z: float | None


class Station(Model):
    station_id: str
    name: str | None
    lat: float
    lon: float
    provider: str | None
    cluster_id: str
    latest: Reading | None


class NeighborEvidence(Model):
    station_id: str
    ts: UTCDateTime
    lag_hours: int
    travel_hours: float
    alignment: float
    rise: float
    reference: float


class PlumeSource(Model):
    station_id: str
    ts: UTCDateTime


class Event(Reading):
    plume_evidence: list[NeighborEvidence]
    plume_sources: list[PlumeSource]


class BatchSummary(Model):
    batch_id: str
    window_start: UTCDateTime
    window_end: UTCDateTime
    record_count: int
    merkle_root: Hash
    tx_hash: str | None
    chain_id: int | None
    anchored_at: UTCDateTime | None
    contract_address: str | None


class ProofStep(Model):
    sibling_hash: Hash
    side: Literal["left", "right"]


class ProofResponse(Model):
    batch: BatchSummary
    leaf_index: int
    record: Record
    canonical_record: str
    record_hash: Hash
    path: list[ProofStep]
    root: Hash


class VerifyRequest(Model):
    batch_id: Identifier
    leaf_index: int = Field(ge=0, strict=True)
    record: Record
    path: list[ProofStep] | None = Field(default=None, max_length=32)


class VerifyResponse(Model):
    verified: bool
    code: Literal["verified", "unanchored", "batch_mismatch", "record_mismatch"]
    reason: str
    batch_id: str
    leaf_index: int
    record_hash: Hash
    on_chain_root: Hash | None
    record_count: int
    chain_id: int
    contract_address: str
    anchored_at: UTCDateTime | None
    tx_hash: str | None


class ErrorResponse(Model):
    detail: str
