"""Read the published Sepolia proof without a local database or signing key."""

import argparse
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
from typing import Any

from ecoproof.config import PROJECT_ROOT, load_settings
from ecoproof.provenance.anchor import (
    AnchorError, Registry, SEPOLIA_CHAIN_ID, public_client, read_record,
)
from ecoproof.provenance.merkle import MerkleProof, canonical_record, hash_record, verify_proof


# Trusted demo identity is explicit, rather than selected by an uploaded proof.
DEMO_REGISTRY = "0xb120d4671607E7C24F6C14C4f23B589F5f4484EB"
DEMO_BATCH = "ecoproof:v1:valid:20261011T230000Z:e7aaf8938d201639002bfed699ed30b73674746c28d460ad4f1ce594aa67efc0"


def utc_seconds(value: str) -> int:
    timestamp = datetime.fromisoformat(value)
    if timestamp.utcoffset() is None:
        raise ValueError("Proof timestamps must include a timezone")
    return int(timestamp.timestamp())


def verify_bundle(bundle: dict[str, Any], registry: Registry, *, record: dict | None = None) -> dict[str, Any]:
    """Authenticate root/count using the registry; never open DuckDB or sign."""
    if registry.chain_id != SEPOLIA_CHAIN_ID or registry.address != DEMO_REGISTRY:
        raise ValueError("The public demo requires its published Sepolia registry")
    batch = bundle["batch"]
    if batch["batch_id"] != DEMO_BATCH:
        raise ValueError("Proof is not for the published demo batch")
    on_chain = registry.read(DEMO_BATCH)
    payload = bundle["record"] if record is None else record
    proof = MerkleProof(bundle["leaf_index"], tuple(
        (bytes.fromhex(step["sibling_hash"]), step["side"]) for step in bundle["path"]
    ))
    metadata_matches = (
        batch["chain_id"] == SEPOLIA_CHAIN_ID
        and batch["contract_address"] == DEMO_REGISTRY
        and bundle["root"] == batch["merkle_root"] == on_chain["root"].hex()
        and batch["record_count"] == on_chain["record_count"]
        and utc_seconds(batch["window_start"]) == on_chain["window_start"]
        and utc_seconds(batch["window_end"]) == on_chain["window_end"]
        and utc_seconds(batch["anchored_at"]) == on_chain["anchored_at"] > 0
        and bundle["canonical_record"] == canonical_record(bundle["record"])
        and bundle["record_hash"] == hash_record(bundle["record"]).hex()
    )
    verified = bool(metadata_matches and verify_proof(
        payload, proof, on_chain["root"], record_count=on_chain["record_count"],
    ))
    return {
        "verified": verified,
        "batch_id": DEMO_BATCH,
        "chain_id": SEPOLIA_CHAIN_ID,
        "contract_address": DEMO_REGISTRY,
        "leaf_index": proof.leaf_index,
        "record_hash": hash_record(payload).hex(),
        "on_chain_root": on_chain["root"].hex(),
        "on_chain_record_count": on_chain["record_count"],
        "reason": "Canonical record matches the public commitment" if verified
                  else "Record, proof or metadata does not match the public commitment",
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proof", type=Path, default=PROJECT_ROOT / "reports/sepolia-proof.json")
    edits = parser.add_mutually_exclusive_group()
    edits.add_argument("--record", type=Path, help="Optional edited twelve-field payload JSON")
    edits.add_argument("--tamper", action="store_true", help="Add 1 to the value in memory; expect exit 1")
    args = parser.parse_args(argv)
    try:
        bundle = read_record(args.proof)
        payload = read_record(args.record) if args.record else dict(bundle["record"])
        if args.tamper:
            payload["value"] += Decimal("1")
        registry = Registry(public_client(load_settings()), DEMO_REGISTRY, chain_id=SEPOLIA_CHAIN_ID)
        result = verify_bundle(bundle, registry, record=payload)
    except Exception as exc:
        # RPC/provider exceptions can contain secret URLs. Never echo their text.
        reason = str(exc) if isinstance(exc, AnchorError) else "Proof check unavailable; check the proof, compiled contract and Sepolia RPC"
        print(json.dumps({"verified": False, "error": reason}))
        raise SystemExit(2) from None
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["verified"] else 1)


if __name__ == "__main__":
    main()
