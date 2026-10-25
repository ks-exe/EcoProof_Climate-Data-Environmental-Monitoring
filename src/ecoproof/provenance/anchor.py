"""Sepolia deployment, durable signed submissions, and on-chain proof checks."""

import argparse
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb
from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3
from web3.exceptions import TransactionNotFound

from ecoproof.config import PROJECT_ROOT, Settings, load_settings
from ecoproof.provenance.batches import Batch, _load_batch, load_batch, prepare_batches
from ecoproof.provenance.merkle import verify_proof


SEPOLIA_CHAIN_ID = 11155111
ARTIFACT = PROJECT_ROOT / "contracts/artifacts/BatchRegistry.sol/BatchRegistry.json"


class AnchorError(Exception):
    """An operator-facing error that contains no RPC credentials or signing key."""


def artifact() -> dict[str, Any]:
    if not ARTIFACT.is_file():
        raise AnchorError("Contract artifact missing; run npm ci and npm run compile in contracts/ first")
    result = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    if not result.get("abi") or not result.get("bytecode", "").startswith("0x"):
        raise AnchorError("Invalid compiled BatchRegistry artifact")
    return result


def check_chain(w3: Web3, chain_id: int) -> None:
    if w3.eth.chain_id != chain_id:
        raise AnchorError(f"RPC chain does not match expected chain ID {chain_id}")


def account_from_key(private_key: str | None) -> LocalAccount:
    if not private_key:
        raise AnchorError("PRIVATE_KEY is unset; configure a funded throwaway Sepolia wallet in local .env")
    try:
        return Account.from_key(private_key)
    except Exception:
        raise AnchorError("PRIVATE_KEY is not a valid Ethereum signing key") from None


def public_client(settings: Settings) -> Web3:
    if not settings.rpc_url:
        raise AnchorError("RPC_URL is unset; configure an Ethereum Sepolia HTTP RPC in local .env")
    # No implicit localhost/default provider or automatic transaction retries.
    w3 = Web3(Web3.HTTPProvider(settings.rpc_url, request_kwargs={"timeout": 15},
                              exception_retry_configuration=None))
    check_chain(w3, SEPOLIA_CHAIN_ID)
    return w3


def sign_call(w3: Web3, call: Any, account: LocalAccount, chain_id: int) -> tuple[str, bytes]:
    check_chain(w3, chain_id)
    balance = w3.eth.get_balance(account.address)
    if balance == 0:
        raise AnchorError(f"Wallet {account.address} has no testnet ETH for gas")
    transaction = call.build_transaction({
        "from": account.address, "nonce": w3.eth.get_transaction_count(account.address, "pending"),
        "chainId": chain_id, "value": 0,
    })
    # Fees and gas come from the RPC estimate; allow 20% gas headroom.
    transaction["gas"] = (int(transaction["gas"]) * 120 + 99) // 100
    fee = transaction.get("maxFeePerGas", transaction.get("gasPrice"))
    if fee is None or transaction["gas"] * fee > balance:
        raise AnchorError("Wallet balance is below the transaction's estimated maximum gas cost")
    signed = account.sign_transaction(transaction)
    return Web3.to_hex(signed.hash), bytes(signed.raw_transaction)


def mine_signed(w3: Web3, tx_hash: str, raw: bytes, *, timeout: float = 120) -> Any:
    """Resume the SAME signed transaction after a crash, timeout, or lost reply."""
    if Web3.to_hex(Web3.keccak(raw)) != tx_hash:
        raise AnchorError("Saved signed transaction does not match its transaction hash")
    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)
    except TransactionNotFound:
        try:
            w3.eth.get_transaction(tx_hash)
        except TransactionNotFound:
            returned = w3.eth.send_raw_transaction(raw)
            if Web3.to_hex(returned) != tx_hash:
                raise AnchorError("RPC returned a different transaction hash; retain the saved submission")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout, poll_latency=1)
    if Web3.to_hex(receipt["transactionHash"]) != tx_hash:
        raise AnchorError("RPC receipt does not match the submitted transaction hash")
    if receipt["status"] != 1:
        raise AnchorError(f"Transaction reverted: {tx_hash}; its saved submission was retained for inspection")
    block = w3.eth.get_block(receipt["blockNumber"])
    if block["hash"] != receipt["blockHash"]:
        raise AnchorError("Receipt block is no longer canonical; rerun after the chain settles")
    return receipt


def _write_journal(path: Path, value: dict[str, Any], *, create: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        if create:
            os.link(temporary, path)  # Atomic create; never replace another deployment intent.
        else:
            os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def deploy_registry(
    w3: Web3, *, private_key: str, chain_id: int, journal: Path, timeout: float = 120,
) -> dict[str, Any]:
    """Deploy once per journal, recording signed intent BEFORE broadcasting.

    Tests inject an isolated local EVM. The public CLI always pins Sepolia.
    """
    check_chain(w3, chain_id)
    account = account_from_key(private_key)
    compiled = artifact()
    fingerprint = sha256(bytes.fromhex(compiled["bytecode"][2:])).hexdigest()
    if journal.exists():
        state = json.loads(journal.read_text(encoding="utf-8"))
        if (state["chain_id"], state["owner"], state["bytecode_sha256"]) != (chain_id, account.address, fingerprint):
            raise AnchorError("Existing deployment journal belongs to a different chain, owner, or compiled contract")
    else:
        factory = w3.eth.contract(abi=compiled["abi"], bytecode=compiled["bytecode"])
        tx_hash, raw = sign_call(w3, factory.constructor(), account, chain_id)
        state = {"status": "pending", "chain_id": chain_id, "owner": account.address,
                 "bytecode_sha256": fingerprint, "tx_hash": tx_hash, "raw_transaction": raw.hex()}
        _write_journal(journal, state, create=True)
    receipt = mine_signed(w3, state["tx_hash"], bytes.fromhex(state["raw_transaction"]), timeout=timeout)
    address = receipt["contractAddress"]
    if not address or not w3.eth.get_code(address):
        raise AnchorError("Deployment receipt has no deployed contract code")
    contract = w3.eth.contract(address=address, abi=compiled["abi"])
    if contract.functions.owner().call() != account.address:
        raise AnchorError("Deployed registry owner differs from the signing wallet")
    state.update(status="mined", contract_address=address, block_number=receipt["blockNumber"],
                 block_hash=Web3.to_hex(receipt["blockHash"]), gas_used=receipt["gasUsed"])
    _write_journal(journal, state)
    return {key: value for key, value in state.items() if key != "raw_transaction"}


def deployment_journal(settings: Settings) -> Path:
    return settings.data_dir / "deployments" / "sepolia.json"


def registry_address(settings: Settings) -> str:
    address = settings.registry_address
    if not address and deployment_journal(settings).is_file():
        state = json.loads(deployment_journal(settings).read_text(encoding="utf-8"))
        if state.get("status") == "mined" and state.get("chain_id") == SEPOLIA_CHAIN_ID:
            address = state.get("contract_address")
    if not address or not Web3.is_address(address):
        raise AnchorError("REGISTRY_ADDRESS is unset/invalid and no mined Sepolia deployment journal is available")
    return Web3.to_checksum_address(address)


class Registry:
    def __init__(self, w3: Web3, address: str, *, chain_id: int) -> None:
        check_chain(w3, chain_id)
        if not Web3.is_address(address):
            raise AnchorError("Registry must be an Ethereum address, not an ENS name")
        self.w3, self.chain_id = w3, chain_id
        self.address = Web3.to_checksum_address(address)
        if not w3.eth.get_code(self.address):
            raise AnchorError("No contract code exists at the configured registry address")
        self.contract = w3.eth.contract(address=self.address, abi=artifact()["abi"])

    def read(self, batch_id: str, *, block: Any = "latest") -> dict[str, Any]:
        check_chain(self.w3, self.chain_id)
        root, start, end, count, at = self.contract.functions.batches(Web3.keccak(text=batch_id)).call(block_identifier=block)
        return {"root": bytes(root), "window_start": start, "window_end": end, "record_count": count, "anchored_at": at}

    def matches(self, batch: Batch, on_chain: dict[str, Any]) -> bool:
        return bool(on_chain["anchored_at"] and on_chain["root"] == batch.tree.root
                    and on_chain["record_count"] == batch.tree.record_count
                    and on_chain["window_start"] == int(batch.window_start.timestamp())
                    and on_chain["window_end"] == int(batch.window_end.timestamp()))

    def confirm(self, batch: Batch, receipt: Any) -> dict[str, Any]:
        if receipt["to"] != self.address:
            raise AnchorError("Anchor receipt belongs to a different contract")
        logs = self.contract.events.BatchAnchored().process_receipt(receipt)
        key = Web3.keccak(text=batch.batch_id)
        matches = [entry for entry in logs if entry["address"] == self.address
                   and entry["args"]["batchKey"] == key and entry["args"]["root"] == batch.tree.root
                   and entry["args"]["count"] == batch.tree.record_count]
        # Current immutable state plus the receipt event/header avoids requiring
        # an archive RPC for historical eth_call when resuming an older batch.
        on_chain = self.read(batch.batch_id)
        timestamp = self.w3.eth.get_block(receipt["blockNumber"])["timestamp"]
        if len(matches) != 1 or not self.matches(batch, on_chain) or on_chain["anchored_at"] != timestamp:
            raise AnchorError("Receipt event or registry readback does not match the stored batch")
        return on_chain


def submit_batch(
    settings: Settings, batch_id: str, registry: Registry, *, private_key: str, timeout: float = 120,
) -> dict[str, Any]:
    """Persist intent, broadcast, verify receipt/readback, then mark the batch mined."""
    account = account_from_key(private_key)
    if registry.contract.functions.owner().call() != account.address:
        raise AnchorError("Signing wallet is not the registry owner")
    # The write connection also prevents competing writer processes on this DB.
    with duckdb.connect(str(settings.duckdb_path)) as db:
        batch = _load_batch(db, batch_id)
        saved = db.execute("""SELECT chain_id, contract_address, tx_hash, raw_transaction
                              FROM gold.anchor_submissions WHERE batch_id = ?""", [batch_id]).fetchone()
        if saved:
            chain, address, tx_hash, raw = saved
            if chain != registry.chain_id or address != registry.address:
                raise AnchorError("Batch already has a submission to a different chain/registry")
        else:
            if registry.read(batch_id)["anchored_at"]:
                raise AnchorError("Batch already exists on-chain without a local submission; recover its original receipt")
            call = registry.contract.functions.anchor(
                Web3.keccak(text=batch_id), batch.tree.root, int(batch.window_start.timestamp()),
                int(batch.window_end.timestamp()), batch.tree.record_count,
            )
            tx_hash, raw = sign_call(registry.w3, call, account, registry.chain_id)
            # Autocommit completes before send_raw_transaction. Signed bytes contain
            # no private key and let a retry reuse the exact hash/nonce/fees.
            db.execute("INSERT INTO gold.anchor_submissions VALUES (?,?,?,?,?)",
                       [batch_id, registry.chain_id, registry.address, tx_hash, raw])
        receipt = mine_signed(registry.w3, tx_hash, raw, timeout=timeout)
        on_chain = registry.confirm(batch, receipt)
        anchored_at = datetime.fromtimestamp(on_chain["anchored_at"], timezone.utc)
        db.execute("UPDATE gold.batches SET tx_hash=?, chain_id=?, anchored_at=? WHERE batch_id=?",
                   [tx_hash, registry.chain_id, anchored_at.replace(tzinfo=None), batch_id])
    return {"status": "mined", "batch_id": batch_id, "tx_hash": tx_hash, "chain_id": registry.chain_id,
            "contract_address": registry.address, "root": batch.tree.root.hex(),
            "record_count": batch.tree.record_count, "anchored_at": anchored_at.isoformat(),
            "block_number": receipt["blockNumber"], "gas_used": receipt["gasUsed"]}


def verify_saved_record(
    settings: Settings, batch_id: str, index: int, registry: Registry, *, record: dict | None = None,
) -> dict[str, Any]:
    batch = load_batch(settings.duckdb_path, batch_id)
    proof = batch.tree.proof(index)
    payload = json.loads(batch.tree.canonical_records[index], parse_float=Decimal) if record is None else record
    on_chain = registry.read(batch_id)
    passed = registry.matches(batch, on_chain) and verify_proof(
        payload, proof, on_chain["root"], record_count=on_chain["record_count"],
    )
    return {"verified": passed, "batch_id": batch_id, "leaf_index": index,
            "chain_id": registry.chain_id, "contract_address": registry.address,
            "reason": "Canonical record matches the on-chain batch" if passed else "Record or batch does not match the on-chain commitment"}


def _unique_json(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise AnchorError("Uploaded record JSON has duplicate keys")
        result[key] = value
    return result


def read_record(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal, object_pairs_hook=_unique_json)
    if not isinstance(payload, dict):
        raise AnchorError("Uploaded record JSON must be an object containing the twelve payload fields")
    return payload


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Prepare, deploy, anchor, and verify EcoProof batches on Ethereum Sepolia")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Snapshot confident VALID Gold rows; no network")
    prepare.add_argument("--start", required=True, type=datetime.fromisoformat)
    prepare.add_argument("--end", required=True, type=datetime.fromisoformat)
    commands.add_parser("deploy", help="Deploy once or resume the saved deployment transaction")
    for name in ("submit", "read", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--batch-id", required=True)
        if name == "verify":
            command.add_argument("--index", type=int, required=True)
            command.add_argument("--record", type=Path, help="Optional edited twelve-field payload JSON")
    args = parser.parse_args(argv)
    settings = load_settings()
    try:
        if args.command == "prepare":
            try:
                batches = prepare_batches(settings, start=args.start, end=args.end)
            except ValueError as exc:
                raise AnchorError(str(exc)) from None
            result = {"status": "prepared" if batches else "no_valid_records", "batch_count": len(batches),
                      "batches": [{"batch_id": batch.batch_id, "root": batch.tree.root.hex(),
                                   "record_count": batch.tree.record_count} for batch in batches]}
        else:
            w3 = public_client(settings)
            if args.command == "deploy":
                account_from_key(settings.private_key)
                result = deploy_registry(w3, private_key=settings.private_key, chain_id=SEPOLIA_CHAIN_ID,
                                         journal=deployment_journal(settings))
            else:
                registry = Registry(w3, registry_address(settings), chain_id=SEPOLIA_CHAIN_ID)
                if args.command == "submit":
                    result = submit_batch(settings, args.batch_id, registry, private_key=settings.private_key)
                elif args.command == "read":
                    result = registry.read(args.batch_id)
                    result["root"] = result["root"].hex()
                else:
                    payload = None if args.record is None else read_record(args.record)
                    result = verify_saved_record(settings, args.batch_id, args.index, registry, record=payload)
        print(json.dumps(result, indent=2))
        if result.get("verified") is False or result.get("status") == "no_valid_records":
            raise SystemExit(1)
    except AnchorError as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, indent=2))
        raise SystemExit(1) from None
    except Exception as exc:
        # Provider/OS errors can embed credential-bearing URLs. Keep raw details
        # out of logs; pending signed intent remains available for safe retry.
        print(json.dumps({"status": "error", "error_type": type(exc).__name__,
                          "reason": "Operation failed; check RPC connectivity and local state. Saved submissions are retained; rerun to resume."}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
