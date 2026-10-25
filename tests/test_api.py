"""Task 9: HTTP behavior, exact uploads, and real verification on a local test EVM."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import json

import duckdb
from fastapi.testclient import TestClient
import pytest
from web3 import Web3

from ecoproof.api import main
from ecoproof.api.main import create_app, get_registry_factory
from ecoproof.config import Settings
from ecoproof.detect.classifier import PlumeEvidence
from ecoproof.provenance.anchor import Registry, deploy_registry, mine_signed, sign_call, submit_batch
from ecoproof.provenance.batches import prepare_batches
from ecoproof.provenance.merkle import MerkleProof, hash_record, verify_proof


@pytest.fixture
def api_data(gold_snapshot):
    settings, start, records, publish = gold_snapshot
    evidence = PlumeEvidence("b", start + timedelta(hours=1), 1, 1.1, .95, 8, 12)
    records = [replace(row, plume_evidence=(evidence,), plume_sources=(("a", start),))
               if row.station_id == "plume" else row for row in records]
    publish(records)
    with duckdb.connect(str(settings.duckdb_path)) as db:
        db.execute("""CREATE SCHEMA silver;
            CREATE TABLE silver.stations(station_id TEXT, name TEXT, lat DOUBLE, lon DOUBLE,
                                         provider TEXT, cluster_id TEXT);""")
        db.executemany("INSERT INTO silver.stations VALUES (?,?,?,?,?,?)", [
            (station, "Synthetic " + station, 28.6, 77.2, "synthetic test fixture", "test")
            for station in sorted({row.station_id for row in records} | {"no-reading"})
        ])
    batches = prepare_batches(settings, start=start, end=start + timedelta(hours=2))
    return settings, start, records, publish, batches


@pytest.fixture
def client(api_data):
    with TestClient(create_app(api_data[0])) as client:
        yield client


def proof_for(client, *, station="a", ts="2026-10-21T00:00:00Z", **extra):
    response = client.get("/proof", params={"station": station, "ts": ts, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def upload_for(proof):
    return {"batch_id": proof["batch"]["batch_id"], "leaf_index": proof["leaf_index"], "record": dict(proof["record"])}


def test_openapi_documents_only_the_six_mvp_routes_and_models(tmp_path):
    settings = Settings(tmp_path / "absent")
    with TestClient(create_app(settings)) as client:
        spec = client.get("/openapi.json")
        assert spec.status_code == 200
        assert set(spec.json()["paths"]) == {"/stations", "/readings", "/events", "/batches", "/proof", "/verify"}
        assert spec.json()["paths"]["/verify"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        schemas = spec.json()["components"]["schemas"]
        record_schema = schemas.get("Record-Input", schemas.get("Record"))
        assert record_schema["properties"]["value"]["type"] == "number"
        for path, operations in spec.json()["paths"].items():
            for operation in operations.values():
                assert operation["responses"]["200"]["content"]["application/json"]["schema"]
                assert "503" in operation["responses"]
        docs = client.get("/docs")
        assert docs.status_code == 200 and "swagger-ui" in docs.text
        assert client.post("/chat", json={}).status_code == 404
        assert client.post("/batches", json={}).status_code == 405
    assert not settings.data_dir.exists()


def test_stations_keep_missing_and_low_confidence_distinct(client):
    response = client.get("/stations")
    assert response.status_code == 200, response.text
    stations = response.json()
    assert [s["station_id"] for s in stations] == sorted(s["station_id"] for s in stations)
    by_id = {s["station_id"]: s for s in stations}
    assert (by_id["a"]["lat"], by_id["a"]["lon"]) == (28.6, 77.2)
    assert by_id["a"]["latest"]["ts"] == "2026-10-21T01:00:00.000000Z"
    assert by_id["no-reading"]["latest"] is None
    assert by_id["low"]["latest"]["low_confidence"] is True
    assert by_id["low"]["latest"]["label"] == "VALID"
    assert by_id["fault"]["latest"]["reason"] == "synthetic fixture"


def test_readings_filter_boundaries_offsets_and_bound_sql(client):
    params = {"station": "a", "from": "2026-10-21T05:00:00+05:00", "to": "2026-10-21T06:00:00+05:00"}
    response = client.get("/readings", params=params)
    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows) == 1 and rows[0]["ts"] == "2026-10-21T00:00:00.000000Z"
    assert (rows[0]["value"], rows[0]["expected"], rows[0]["z"], rows[0]["label"]) == (12.5, 12, .25, "VALID")
    assert rows[0]["neighbor_count"] == 2 and rows[0]["batch_id"]
    params["station"] = "' OR 1=1; DROP TABLE gold.batches; --"
    assert client.get("/readings", params=params).json() == []
    assert len(client.get("/batches").json()) == 2


@pytest.mark.parametrize("start,end", [
    ("2026-10-21", "2026-10-22T00:00:00Z"),
    ("2026-10-21T00:00:00", "2026-10-22T00:00:00Z"),
    ("1792540800", "2026-10-22T00:00:00Z"),
    ("2026-10-21T00:00:00.0000001Z", "2026-10-22T00:00:00Z"),
    ("2026-10-21T00:00:00Z", "2026-10-21T00:00:00Z"),
    ("2026-10-22T00:00:00Z", "2026-10-21T00:00:00Z"),
    ("2026-10-21T00:00:00Z", "2026-11-22T00:00:00Z"),
])
def test_invalid_time_windows_rejected_before_reading_data(tmp_path, start, end):
    with TestClient(create_app(Settings(tmp_path / "absent"))) as client:
        assert client.get("/readings", params={"station": "a", "from": start, "to": end}).status_code == 422


def test_events_report_saved_wind_and_neighbor_evidence(client):
    response = client.get("/events")
    assert response.status_code == 200, response.text
    events = response.json()
    assert [event["station_id"] for event in events] == ["fault", "plume"]
    assert events[0]["plume_evidence"] == []  # Do not invent per-neighbor fault evidence.
    assert events[1]["wind_speed"] == 2 and events[1]["wind_dir_deg"] == 270
    assert events[1]["plume_evidence"][0]["station_id"] == "b"
    assert events[1]["plume_evidence"][0]["rise"] == 8
    assert events[1]["plume_sources"] == [{"station_id": "a", "ts": "2026-10-21T00:00:00Z"}]
    assert len(client.get("/events", params={"label": "VERIFIED_PLUME_EVENT"}).json()) == 1
    assert len(client.get("/events", params={"limit": 1}).json()) == 1


@pytest.mark.parametrize("path", ["/events?label=VALID", "/events?label=unknown", "/events?limit=0",
                                  "/events?limit=1001", "/batches?offset=-1", "/batches?limit=1001"])
def test_invalid_filters(tmp_path, path):
    with TestClient(create_app(Settings(tmp_path / "absent"))) as client:
        assert client.get(path).status_code == 422


def test_unmined_batches_have_null_chain_fields_and_proofs_recompute(client):
    rows = client.get("/batches").json()
    assert [row["record_count"] for row in rows] == [1, 3]
    assert all(row["tx_hash"] is None and row["anchored_at"] is None and row["chain_id"] is None for row in rows)
    assert client.get("/batches", params={"offset": 1, "limit": 1}).json() == rows[1:]
    for station, ts in [("c", "2026-10-21T00:00:00Z"), ("a", "2026-10-21T01:00:00Z")]:
        proof = proof_for(client, station=station, ts=ts)
        record = json.loads(proof["canonical_record"], parse_float=Decimal)
        assert hash_record(record).hex() == proof["record_hash"]
        path = MerkleProof(proof["leaf_index"], tuple((bytes.fromhex(p["sibling_hash"]), p["side"]) for p in proof["path"]))
        assert verify_proof(record, path, bytes.fromhex(proof["root"]), record_count=proof["batch"]["record_count"])
        assert json.loads(proof["canonical_record"]) == proof["record"]


def test_proof_excludes_ineligible_rows_and_accepts_timezone_offsets(client):
    assert proof_for(client, ts="2026-10-21T05:00:00+05:00") == proof_for(client)
    for station in ("low", "fault", "plume", "unknown"):
        assert client.get("/proof", params={"station": station, "ts": "2026-10-21T00:00:00Z"}).status_code == 404
    assert client.get("/proof", params={"station": "a", "ts": "2026-10-21T00:00:00Z", "batch_id": "unknown"}).status_code == 404


def test_old_snapshot_explicitly_available_after_gold_rebuild(api_data, client):
    settings, start, records, publish, _ = api_data
    old = proof_for(client)
    publish([replace(record, value=record.value + 1) for record in records])
    assert client.get("/proof", params={"station": "a", "ts": start.isoformat()}).status_code == 404
    assert proof_for(client, batch_id=old["batch"]["batch_id"]) == old
    # Explicit history also works when current Gold views are absent.
    with duckdb.connect(str(settings.duckdb_path)) as db:
        db.execute("DROP VIEW gold.classified; DROP VIEW gold.classification_evidence")
    assert proof_for(client, batch_id=old["batch"]["batch_id"]) == old
    assert all(station["latest"] is None for station in client.get("/stations").json())


def test_missing_database_is_honest_and_readonly(tmp_path):
    settings = Settings(tmp_path / "missing")
    with TestClient(create_app(settings)) as client:
        for route in ("/stations", "/events", "/batches", "/proof?station=a&ts=2026-10-21T00:00:00Z",
                      "/readings?station=a&from=2026-10-21T00:00:00Z&to=2026-10-22T00:00:00Z"):
            response = client.get(route)
            assert response.status_code == 503, response.text
            assert str(tmp_path) not in response.text
    assert not settings.data_dir.exists()


def test_empty_silver_and_missing_gold(tmp_path):
    settings = Settings(tmp_path)
    with duckdb.connect(str(settings.duckdb_path)) as db:
        db.execute("CREATE SCHEMA silver; CREATE TABLE silver.stations(station_id TEXT)")
    with TestClient(create_app(settings)) as client:
        assert client.get("/stations").json() == []
        assert client.get("/events").status_code == 503
        assert client.get("/batches").status_code == 503


def test_filesystem_permission_error_is_sanitized(tmp_path, monkeypatch):
    settings = Settings(tmp_path)

    def denied(path):
        raise PermissionError("SENTINEL_PRIVATE_PATH")

    with TestClient(create_app(settings)) as client:
        with monkeypatch.context() as patch:
            patch.setattr(type(settings.duckdb_path), "is_file", denied)
            response = client.get("/stations")
    assert response.status_code == 503
    assert "SENTINEL_PRIVATE_PATH" not in response.text


def test_corrupt_snapshot_and_missing_evidence_are_not_served(api_data, client):
    settings, _, _, _, batches = api_data
    with duckdb.connect(str(settings.duckdb_path)) as db:
        db.execute("UPDATE gold.batch_records SET record_hash='corrupt' WHERE batch_id=? AND leaf_index=0", [batches[0].batch_id])
    response = client.get("/proof", params={"station": "a", "ts": "2026-10-21T00:00:00Z"})
    assert response.status_code == 404  # Current hash no longer has a matching batch link.
    response = client.get("/proof", params={"station": "a", "ts": "2026-10-21T00:00:00Z",
                                           "batch_id": batches[0].batch_id})
    assert response.status_code == 409
    with duckdb.connect(str(settings.duckdb_path)) as db:
        db.execute("CREATE OR REPLACE VIEW gold.classification_evidence AS SELECT 'a' AS station_id, TIMESTAMP '2026-10-21' AS ts")
    assert client.get("/stations").status_code == 503


def minimal_upload():
    return {"batch_id": "synthetic", "leaf_index": 0, "record": {
        "station_id": "a", "ts": "2026-10-21T00:00:00Z", "value": 12.5, "expected": 12,
        "residual": .5, "z": .25, "label": "VALID", "neighbor_count": 2,
        "wind_speed": 2, "wind_dir_deg": 270, "low_confidence": False, "reason": "synthetic",
    }}


@pytest.mark.parametrize("content", ["null", "[]", "12", '"record"', "{", "{}", '{"x":1,"x":2}',
    json.dumps(minimal_upload()).replace('"value": 12.5', '"value": 12.5,"value": 13'),
    json.dumps(minimal_upload()).replace('"value": 12.5', '"value": NaN'),
    json.dumps(minimal_upload()).replace('"value": 12.5', '"value": Infinity'),
    json.dumps(minimal_upload()).replace('"value": 12.5', '"value": 1e10000'),
])
def test_ambiguous_or_nonobject_upload_is_rejected(tmp_path, content):
    with TestClient(create_app(Settings(tmp_path / "absent"))) as client:
        response = client.post("/verify", content=content, headers={"Content-Type": "application/json"})
        assert response.status_code == 422, response.text


@pytest.mark.parametrize("field,value", [("value", "12.5"), ("value", True), ("value", None),
    ("low_confidence", "false"), ("neighbor_count", True), ("neighbor_count", 2.0),
    ("ts", "2026-10-21T00:00:00"), ("label", "healthy"), ("reason", ""), ("extra", "SENTINEL_SECRET")])
def test_upload_types_cannot_be_silently_coerced(tmp_path, field, value):
    upload = minimal_upload()
    upload["record"][field] = value
    with TestClient(create_app(Settings(tmp_path / "absent"))) as client:
        response = client.post("/verify", json=upload)
        assert response.status_code == 422, response.text
        assert "SENTINEL_SECRET" not in response.text


def test_upload_limits_and_content_type(tmp_path):
    with TestClient(create_app(Settings(tmp_path / "absent"))) as client:
        assert client.post("/verify", content="{}").status_code == 415
        assert client.post("/verify", content=b" " * 65537, headers={"Content-Type": "application/json"}).status_code == 413
        assert client.post("/verify", content=b'\xff', headers={"Content-Type": "application/json"}).status_code == 422
        upload = minimal_upload()
        upload["leaf_index"] = True
        assert client.post("/verify", json=upload).status_code == 422
        upload["leaf_index"] = 0
        upload["root"] = "0" * 64
        assert client.post("/verify", json=upload).status_code == 422


def test_missing_or_unavailable_rpc_does_not_leak_credentials(client, monkeypatch):
    upload = upload_for(proof_for(client))
    assert client.post("/verify", json=upload).status_code == 503

    def unavailable(settings):
        raise ConnectionError("https://rpc.invalid/SENTINEL_SECRET")

    monkeypatch.setattr(main, "public_client", unavailable)
    response = client.post("/verify", json=upload)
    assert response.status_code == 503 and "SENTINEL_SECRET" not in response.text
    upload["batch_id"] = "unknown"
    assert client.post("/verify", json=upload).status_code == 404
    upload["batch_id"] = proof_for(client)["batch"]["batch_id"]
    upload["leaf_index"] = 3
    assert client.post("/verify", json=upload).status_code == 404


@pytest.fixture
def registry(local_evm, tmp_path):
    w3, account = local_evm
    deployment = deploy_registry(w3, private_key=Web3.to_hex(account.key), chain_id=31337, journal=tmp_path / "local-deploy.json")
    return Registry(w3, deployment["contract_address"], chain_id=31337), account


def test_verify_reads_real_local_evm_and_detects_tampering(api_data, client, registry):
    settings, _, records, publish, batches = api_data
    chain, account = registry
    client.app.dependency_overrides[get_registry_factory] = lambda: lambda: chain
    proof = proof_for(client, station="c")  # Odd-node duplicate path.
    upload = upload_for(proof)
    response = client.post("/verify", json=upload)
    assert response.status_code == 200 and response.json()["code"] == "unanchored"
    assert response.json()["verified"] is False and response.json()["on_chain_root"] is None
    mined = submit_batch(settings, batches[0].batch_id, chain, private_key=Web3.to_hex(account.key))
    nonce = chain.w3.eth.get_transaction_count(account.address)
    response = client.post("/verify", json=upload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["verified"] and result["code"] == "verified"
    assert result["on_chain_root"] == chain.read(batches[0].batch_id)["root"].hex()
    assert result["tx_hash"] == mined["tx_hash"] and result["chain_id"] == 31337
    assert result["record_count"] == 3 and result["anchored_at"].endswith("Z")
    assert "raw_transaction" not in response.text
    upload["path"] = proof["path"]
    assert client.post("/verify", json=upload).json()["verified"]
    upload["path"][0]["sibling_hash"] = "0" * 64
    assert client.post("/verify", json=upload).json()["code"] == "record_mismatch"
    upload.pop("path")
    upload["record"]["value"] += .0001
    result = client.post("/verify", json=upload).json()
    assert not result["verified"] and result["code"] == "record_mismatch"
    assert result["record_hash"] != proof["record_hash"]
    assert chain.w3.eth.get_transaction_count(account.address) == nonce  # HTTP performs no writes.
    listed = client.get("/batches").json()[1]
    assert listed["tx_hash"] == mined["tx_hash"] and listed["contract_address"] == chain.address
    assert "raw_transaction" not in json.dumps(listed)
    publish([replace(record, value=record.value + 1) for record in records])
    assert client.post("/verify", json=upload_for(proof)).json()["verified"]


def test_single_leaf_verification_and_exact_decimal_upload(api_data, client, registry):
    settings, _, _, _, batches = api_data
    chain, account = registry
    submit_batch(settings, batches[1].batch_id, chain, private_key=Web3.to_hex(account.key))
    client.app.dependency_overrides[get_registry_factory] = lambda: lambda: chain
    proof = proof_for(client, ts="2026-10-21T01:00:00Z")
    assert proof["path"] == []
    upload = upload_for(proof)
    upload["path"] = []
    upload["record"]["ts"] = "2026-10-21T06:00:00+05:00"
    assert client.post("/verify", json=upload).json()["verified"]
    # Binary float loses the difference on either side of the halfway decimal.
    # The above-halfway decimal MUST fail; below-halfway still rounds to 12.5000.
    body = json.dumps(upload).replace('"value": 12.5', '"value": 12.500050000000000000001')
    result = client.post("/verify", content=body, headers={"Content-Type": "application/json"}).json()
    assert result["code"] == "record_mismatch"
    body = body.replace('12.500050000000000000001', '12.500049999999999999999')
    assert client.post("/verify", content=body, headers={"Content-Type": "application/json"}).json()["verified"]


def test_on_chain_count_is_trusted_over_local_metadata(api_data, client, registry):
    _, _, _, _, batches = api_data
    chain, account = registry
    batch = batches[0]
    call = chain.contract.functions.anchor(Web3.keccak(text=batch.batch_id), batch.tree.root,
                int(batch.window_start.timestamp()), int(batch.window_end.timestamp()), 4)
    tx_hash, raw = sign_call(chain.w3, call, account, 31337)
    mine_signed(chain.w3, tx_hash, raw)
    client.app.dependency_overrides[get_registry_factory] = lambda: lambda: chain
    response = client.post("/verify", json=upload_for(proof_for(client)))
    assert response.status_code == 200
    assert response.json()["code"] == "batch_mismatch" and not response.json()["verified"]
    assert response.json()["record_count"] == 4


def test_saved_registry_binding_is_enforced(api_data, client, registry):
    settings, _, _, _, batches = api_data
    chain, account = registry
    submit_batch(settings, batches[0].batch_id, chain, private_key=Web3.to_hex(account.key))
    client.app.dependency_overrides[get_registry_factory] = lambda: lambda: chain
    upload = upload_for(proof_for(client))
    with duckdb.connect(str(settings.duckdb_path)) as db:
        db.execute("UPDATE gold.anchor_submissions SET contract_address=?", [account.address])
    response = client.post("/verify", json=upload)
    assert response.status_code == 409 and "different chain or registry" in response.json()["detail"]


def test_default_client_pins_sepolia_and_read_failure_is_unavailable(client, registry, monkeypatch):
    chain, _ = registry
    upload = upload_for(proof_for(client))
    monkeypatch.setattr(main, "public_client", lambda _: chain.w3)
    monkeypatch.setattr(main, "registry_address", lambda _: chain.address)
    assert client.post("/verify", json=upload).status_code == 503  # Local chain is not Sepolia.
    client.app.dependency_overrides[get_registry_factory] = lambda: lambda: chain

    def unavailable(batch_id):
        raise TimeoutError("https://rpc.invalid/SENTINEL_SECRET")

    monkeypatch.setattr(chain, "read", unavailable)
    response = client.post("/verify", json=upload)
    assert response.status_code == 503 and "SENTINEL_SECRET" not in response.text
