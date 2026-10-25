"""Task 8 fixtures: synthetic Gold and an isolated, ephemeral local EVM."""

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from uuid import uuid4

import pytest

from ecoproof.config import PROJECT_ROOT, Settings
from ecoproof.detect.classifier import Classification, DetectionRun
from ecoproof.transform.gold import _write_parquet, publish_classifications


def pytest_sessionstart(session: pytest.Session) -> None:
    """Create a nested --basetemp parent before the first tmp_path fixture."""
    base = session.config.getoption("basetemp")
    if base is not None:
        path = Path(base)
        if not path.is_absolute():
            path = session.config.invocation_params.dir / path
        # pytest creates/recreates the final directory, but not its parents.
        path.parent.mkdir(parents=True, exist_ok=True)


@pytest.fixture
def gold_snapshot(tmp_path: Path):
    settings = Settings(tmp_path / "synthetic-data")
    start = datetime(2026, 10, 21, tzinfo=timezone.utc)

    def row(station: str, *, hour: int = 0, low: bool = False, label: str = "VALID"):
        return Classification(station, start + timedelta(hours=hour), 12.5, 12, .5, .25,
                              label, 2, 2, 270, low, "synthetic fixture", 2, .25)

    records = [row("a"), row("b"), row("c"), row("low", low=True),
               row("fault", label="SENSOR_FAULT_DRIFT"), row("plume", label="VERIFIED_PLUME_EVENT"),
               row("a", hour=1)]

    def publish(items):
        directory = settings.gold_dir / f"build-{uuid4().hex}"
        directory.mkdir(parents=True)
        _write_parquet(DetectionRun(tuple(items), {}), directory)
        publish_classifications(settings.duckdb_path, directory)
        return directory

    publish(records)
    return settings, start, records, publish


@pytest.fixture(scope="session")
def local_evm():
    from eth_account import Account
    from web3 import Web3

    node = shutil.which("node")
    cli = PROJECT_ROOT / "contracts/node_modules/hardhat/dist/src/cli.js"
    if not node or not cli.is_file():
        pytest.fail("Contract integration tests require Node >=22.13 and npm ci in contracts/")
    env = dict(os.environ)
    for name in ("PRIVATE_KEY", "RPC_URL", "OPENAQ_API_KEY", "REGISTRY_ADDRESS", "ECOPROOF_LOCAL_TEST_KEY"):
        env.pop(name, None)
    subprocess.run([node, str(cli), "compile", "BatchRegistry.sol"], cwd=PROJECT_ROOT / "contracts", env=env,
                   check=True, capture_output=True, text=True, timeout=90)
    account = Account.create()  # Random, local-test-only key; never saved to .env or logs.
    env["ECOPROOF_LOCAL_TEST_KEY"] = Web3.to_hex(account.key)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    process = subprocess.Popen(
        [node, str(cli), "node", "--network", "default", "--hostname", "127.0.0.1", "--port", str(port)],
        cwd=PROJECT_ROOT / "contracts", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    w3 = Web3(Web3.HTTPProvider(f"http://127.0.0.1:{port}", request_kwargs={"timeout": 2},
                              exception_retry_configuration=None))
    try:
        deadline = time.monotonic() + 30
        while not w3.is_connected():
            if process.poll() is not None or time.monotonic() >= deadline:
                pytest.fail("Isolated Hardhat node did not start; no public network was contacted")
            time.sleep(.2)
        assert w3.eth.chain_id == 31337
        assert w3.eth.accounts == [account.address]
        yield w3, account
    finally:
        process.terminate()
        process.wait(timeout=15)
