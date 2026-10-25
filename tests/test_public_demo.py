"""Portable proof checks use public artifacts and a controlled registry read."""

from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import runpy
from types import SimpleNamespace

import pytest

from ecoproof.config import PROJECT_ROOT
from ecoproof.provenance.anchor import read_record


SCRIPT = runpy.run_path(str(PROJECT_ROOT / "scripts/verify_public_demo.py"))


@pytest.fixture
def proof_and_registry():
    bundle = read_record(PROJECT_ROOT / "reports/sepolia-proof.json")
    batch = bundle["batch"]
    chain = {"root": bytes.fromhex(batch["merkle_root"]), "record_count": 7,
             **{field: int(datetime.fromisoformat(batch[field]).timestamp())
                for field in ("window_start", "window_end", "anchored_at")}}
    reads = []

    def read(batch_id):
        reads.append(batch_id)
        return chain

    registry = SimpleNamespace(chain_id=11155111, address=SCRIPT["DEMO_REGISTRY"], read=read)
    return bundle, registry, chain, reads


def test_original_and_edited_payload_without_database(proof_and_registry):
    bundle, registry, _, reads = proof_and_registry
    original = deepcopy(bundle)
    assert SCRIPT["verify_bundle"](bundle, registry)["verified"] is True
    edited = {**bundle["record"], "value": Decimal("23")}
    assert SCRIPT["verify_bundle"](bundle, registry, record=edited)["verified"] is False
    assert reads == [SCRIPT["DEMO_BATCH"]] * 2
    assert bundle == original


@pytest.mark.parametrize("field,value", [
    ("root", bytes(32)), ("record_count", 8), ("anchored_at", 0),
    ("window_start", 0), ("window_end", 0),
])
def test_chain_state_overrules_saved_claims(proof_and_registry, field, value):
    bundle, registry, chain, _ = proof_and_registry
    chain[field] = value
    assert SCRIPT["verify_bundle"](bundle, registry)["verified"] is False


@pytest.mark.parametrize("edit", ["sibling", "side", "index", "canonical", "hash", "identity"])
def test_modified_proof_is_rejected(proof_and_registry, edit):
    bundle, registry, _, _ = proof_and_registry
    if edit == "sibling":
        bundle["path"][0]["sibling_hash"] = "00" * 32
    elif edit == "side":
        bundle["path"][0]["side"] = "left"
    elif edit == "index":
        bundle["leaf_index"] = 1
    elif edit == "canonical":
        bundle["canonical_record"] = "{}"
    elif edit == "hash":
        bundle["record_hash"] = "00" * 32
    else:
        bundle["batch"]["contract_address"] = "0x" + "00" * 20
    assert SCRIPT["verify_bundle"](bundle, registry)["verified"] is False


def test_rpc_errors_do_not_disclose_credentials(monkeypatch, capsys):
    def unavailable(_settings):
        raise RuntimeError("https://provider.invalid/secret-test-token")

    monkeypatch.setitem(SCRIPT["main"].__globals__, "public_client", unavailable)
    with pytest.raises(SystemExit, match="2"):
        SCRIPT["main"]([])
    output = capsys.readouterr().out
    assert "secret-test-token" not in output
    assert "unavailable" in output
