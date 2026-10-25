"""Real execution on an isolated local EVM; no public testnet result is implied."""

from datetime import timedelta
import json

import duckdb
from eth_account import Account
import pytest
from web3 import Web3

from ecoproof.config import Settings
from ecoproof.provenance import anchor
from ecoproof.provenance.anchor import AnchorError, Registry, deploy_registry, submit_batch, verify_saved_record
from ecoproof.provenance.batches import prepare_batches


@pytest.fixture
def deployed(local_evm, tmp_path):
    w3, account = local_evm
    journal = tmp_path / "deploy" / "local.json"
    result = deploy_registry(w3, private_key=Web3.to_hex(account.key), chain_id=31337, journal=journal)
    return Registry(w3, result["contract_address"], chain_id=31337), account, journal, result


def prepared(gold_snapshot):
    settings, start, _, _ = gold_snapshot
    return settings, prepare_batches(settings, start=start, end=start + timedelta(hours=1))[0]


def query(settings, sql):
    with duckdb.connect(str(settings.duckdb_path), read_only=True) as db:
        return db.execute(sql).fetchall()


def test_deployment_receipt_owner_code_and_idempotent_resume(deployed):
    registry, account, journal, result = deployed
    w3 = registry.w3
    assert result["status"] == "mined"
    assert w3.eth.get_code(result["contract_address"])
    assert w3.eth.get_transaction_receipt(result["tx_hash"])["status"] == 1
    assert registry.contract.functions.owner().call() == account.address
    nonce = w3.eth.get_transaction_count(account.address)
    again = deploy_registry(w3, private_key=Web3.to_hex(account.key), chain_id=31337, journal=journal)
    assert again == result
    assert w3.eth.get_transaction_count(account.address) == nonce
    assert Web3.to_hex(account.key) not in journal.read_text()
    assert "raw_transaction" not in result


def test_submit_readback_persisted_receipt_and_live_proof(deployed, gold_snapshot):
    registry, account, _, _ = deployed
    settings, batch = prepared(gold_snapshot)
    result = submit_batch(settings, batch.batch_id, registry, private_key=Web3.to_hex(account.key))
    on_chain = registry.read(batch.batch_id)
    assert registry.matches(batch, on_chain)
    assert result["tx_hash"].startswith("0x") and len(result["tx_hash"]) == 66
    receipt = registry.w3.eth.get_transaction_receipt(result["tx_hash"])
    assert result["gas_used"] == receipt["gasUsed"] and receipt["status"] == 1
    assert query(settings, "SELECT tx_hash,chain_id FROM gold.batches") == [(result["tx_hash"], 31337)]
    assert query(settings, "SELECT count(anchored_at) FROM gold.batches") == [(1,)]
    assert verify_saved_record(settings, batch.batch_id, 1, registry)["verified"]
    payload = json.loads(batch.tree.canonical_records[1])
    payload["value"] = 12.5001
    assert not verify_saved_record(settings, batch.batch_id, 1, registry, record=payload)["verified"]
    nonce = registry.w3.eth.get_transaction_count(account.address)
    assert submit_batch(settings, batch.batch_id, registry, private_key=Web3.to_hex(account.key)) == result
    assert registry.w3.eth.get_transaction_count(account.address) == nonce


def test_unanchored_local_batch_cannot_pass_chain_verification(deployed, gold_snapshot):
    registry, _, _, _ = deployed
    settings, batch = prepared(gold_snapshot)
    assert not verify_saved_record(settings, batch.batch_id, 0, registry)["verified"]
    assert registry.read(batch.batch_id)["anchored_at"] == 0


@pytest.mark.parametrize("lost_at", ["before_broadcast", "after_mining"])
def test_anchor_recovers_exact_signed_transaction_after_interruption(deployed, gold_snapshot, monkeypatch, lost_at):
    registry, account, _, _ = deployed
    settings, batch = prepared(gold_snapshot)
    original = anchor.mine_signed

    def interrupted(*args, **kwargs):
        if lost_at == "after_mining":
            original(*args, **kwargs)
        raise TimeoutError("synthetic interrupted response")

    monkeypatch.setattr(anchor, "mine_signed", interrupted)
    with pytest.raises(TimeoutError):
        submit_batch(settings, batch.batch_id, registry, private_key=Web3.to_hex(account.key))
    tx_hash = query(settings, "SELECT tx_hash FROM gold.anchor_submissions")[0][0]
    assert query(settings, "SELECT tx_hash,anchored_at FROM gold.batches") == [(None, None)]
    nonce = registry.w3.eth.get_transaction_count(account.address)
    monkeypatch.setattr(anchor, "mine_signed", original)
    result = submit_batch(settings, batch.batch_id, registry, private_key=Web3.to_hex(account.key))
    assert result["tx_hash"] == tx_hash
    assert registry.w3.eth.get_transaction_count(account.address) == nonce + (lost_at == "before_broadcast")
    assert query(settings, "SELECT count(*) FROM gold.anchor_submissions") == [(1,)]


def test_deployment_intent_recovers_after_lost_reply(local_evm, tmp_path, monkeypatch):
    w3, account = local_evm
    journal = tmp_path / "deployment.json"
    original = anchor.mine_signed

    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise TimeoutError("synthetic lost deployment response")

    monkeypatch.setattr(anchor, "mine_signed", interrupted)
    with pytest.raises(TimeoutError):
        deploy_registry(w3, private_key=Web3.to_hex(account.key), chain_id=31337, journal=journal)
    pending = json.loads(journal.read_text())
    assert pending["status"] == "pending"
    nonce = w3.eth.get_transaction_count(account.address)
    monkeypatch.setattr(anchor, "mine_signed", original)
    result = deploy_registry(w3, private_key=Web3.to_hex(account.key), chain_id=31337, journal=journal)
    assert result["tx_hash"] == pending["tx_hash"]
    assert w3.eth.get_transaction_count(account.address) == nonce


def test_duplicate_transaction_really_reverts_in_evm(deployed, gold_snapshot):
    registry, account, _, _ = deployed
    settings, batch = prepared(gold_snapshot)
    first = submit_batch(settings, batch.batch_id, registry, private_key=Web3.to_hex(account.key))
    call = registry.contract.functions.anchor(Web3.keccak(text=batch.batch_id), batch.tree.root,
                                             int(batch.window_start.timestamp()), int(batch.window_end.timestamp()), 3)
    # Explicit gas bypasses preflight estimation so the EVM actually mines a revert.
    transaction = call.build_transaction({"from": account.address, "chainId": 31337, "gas": 200000,
                                         "nonce": registry.w3.eth.get_transaction_count(account.address, "pending")})
    signed = account.sign_transaction(transaction)
    with pytest.raises(AnchorError, match="reverted"):
        anchor.mine_signed(registry.w3, Web3.to_hex(signed.hash), bytes(signed.raw_transaction))
    assert registry.w3.eth.get_transaction_receipt(signed.hash)["status"] == 0
    assert registry.matches(batch, registry.read(batch.batch_id))
    assert query(settings, "SELECT tx_hash FROM gold.batches") == [(first["tx_hash"],)]


def test_failed_readback_does_not_mark_batch_mined_and_can_resume(deployed, gold_snapshot, monkeypatch):
    registry, account, _, _ = deployed
    settings, batch = prepared(gold_snapshot)
    original = registry.confirm

    def mismatch(*args):
        raise AnchorError("synthetic readback mismatch")

    monkeypatch.setattr(registry, "confirm", mismatch)
    with pytest.raises(AnchorError, match="mismatch"):
        submit_batch(settings, batch.batch_id, registry, private_key=Web3.to_hex(account.key))
    assert query(settings, "SELECT tx_hash FROM gold.batches") == [(None,)]
    saved = query(settings, "SELECT tx_hash FROM gold.anchor_submissions")[0][0]
    monkeypatch.setattr(registry, "confirm", original)
    assert submit_batch(settings, batch.batch_id, registry, private_key=Web3.to_hex(account.key))["tx_hash"] == saved


def test_wrong_chain_nonowner_and_missing_contract_fail_before_sending(deployed, gold_snapshot):
    registry, account, _, _ = deployed
    settings, batch = prepared(gold_snapshot)
    before = registry.w3.eth.get_transaction_count(account.address)
    with pytest.raises(AnchorError, match="chain"):
        Registry(registry.w3, registry.address, chain_id=1)
    with pytest.raises(AnchorError, match="No contract code"):
        Registry(registry.w3, account.address, chain_id=31337)
    with pytest.raises(AnchorError, match="not the registry owner"):
        submit_batch(settings, batch.batch_id, registry, private_key=Web3.to_hex(Account.create().key))
    assert registry.w3.eth.get_transaction_count(account.address) == before
    assert query(settings, "SELECT count(*) FROM gold.anchor_submissions") == [(0,)]


def test_saved_submission_cannot_be_redirected_to_another_registry(deployed, gold_snapshot, tmp_path):
    registry, account, _, _ = deployed
    settings, batch = prepared(gold_snapshot)
    submit_batch(settings, batch.batch_id, registry, private_key=Web3.to_hex(account.key))
    second = deploy_registry(registry.w3, private_key=Web3.to_hex(account.key), chain_id=31337,
                             journal=tmp_path / "second.json")
    other = Registry(registry.w3, second["contract_address"], chain_id=31337)
    with pytest.raises(AnchorError, match="different chain/registry"):
        submit_batch(settings, batch.batch_id, other, private_key=Web3.to_hex(account.key))
    assert other.read(batch.batch_id)["anchored_at"] == 0


def test_corrupt_signed_bytes_cannot_be_broadcast(deployed):
    registry, _, _, _ = deployed
    with pytest.raises(AnchorError, match="does not match"):
        anchor.mine_signed(registry.w3, "0x" + "0" * 64, b"corrupt")


def test_deployment_journal_rejects_different_owner(deployed):
    registry, _, journal, _ = deployed
    with pytest.raises(AnchorError, match="different chain, owner"):
        deploy_registry(registry.w3, private_key=Web3.to_hex(Account.create().key), chain_id=31337, journal=journal)


def test_deployment_journal_failure_prevents_broadcast(local_evm, tmp_path, monkeypatch):
    w3, account = local_evm
    nonce = w3.eth.get_transaction_count(account.address)

    def disk_failure(*args, **kwargs):
        raise OSError("synthetic journal failure")

    monkeypatch.setattr(anchor, "_write_journal", disk_failure)
    with pytest.raises(OSError):
        deploy_registry(w3, private_key=Web3.to_hex(account.key), chain_id=31337, journal=tmp_path / "failed.json")
    assert w3.eth.get_transaction_count(account.address) == nonce


def test_cli_missing_configuration_and_provider_error_do_not_leak_secrets(tmp_path, monkeypatch, capsys):
    settings = Settings(tmp_path / "data")
    monkeypatch.setattr(anchor, "load_settings", lambda: settings)
    with pytest.raises(SystemExit) as exc:
        anchor.main(["deploy"])
    assert exc.value.code == 1
    assert "RPC_URL is unset" in capsys.readouterr().out

    def unavailable(_):
        raise ConnectionError("https://rpc.invalid/SYNTHETIC_SECRET_SENTINEL")

    monkeypatch.setattr(anchor, "public_client", unavailable)
    with pytest.raises(SystemExit):
        anchor.main(["deploy"])
    output = capsys.readouterr().out
    assert "SYNTHETIC_SECRET_SENTINEL" not in output
    assert json.loads(output)["error_type"] == "ConnectionError"
    assert not settings.data_dir.exists()


def test_cli_prepare_has_no_network_and_reports_missing_gold(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(anchor, "load_settings", lambda: Settings(tmp_path / "missing"))
    monkeypatch.setattr(anchor, "public_client", lambda _: pytest.fail("prepare must not contact a network"))
    with pytest.raises(SystemExit) as exc:
        anchor.main(["prepare", "--start", "2026-10-21T00:00:00Z", "--end", "2026-10-21T01:00:00Z"])
    assert exc.value.code == 1
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"


def test_invalid_key_and_duplicate_json_fields_are_rejected():
    for key in (None, "synthetic-not-a-wallet"):
        with pytest.raises(AnchorError):
            anchor.account_from_key(key)
    with pytest.raises(AnchorError, match="duplicate"):
        json.loads('{"value":1,"value":2}', object_pairs_hook=anchor._unique_json)


@pytest.mark.parametrize("content", ["null", "[]", "12", '"value"'])
def test_upload_requires_a_json_object_instead_of_falling_back_to_stored_record(tmp_path, content):
    path = tmp_path / "record.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(AnchorError, match="must be an object"):
        anchor.read_record(path)
