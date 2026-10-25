"""Browser acceptance against FastAPI, saved synthetic data, and an actual local EVM.

Requires `npm ci` and `npm run build` in web/ plus installed Chrome (or an explicit
ECOPROOF_BROWSER_CHANNEL). No public network or real-data results are substituted.
"""

from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time

import duckdb
import httpx
import pytest
import uvicorn
from web3 import Web3

from ecoproof.api.main import create_app, get_registry_factory
from ecoproof.config import PROJECT_ROOT
from ecoproof.detect.classifier import PlumeEvidence
from ecoproof.provenance.anchor import Registry, deploy_registry, submit_batch
from ecoproof.provenance.batches import prepare_batches


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


@contextmanager
def api_server(app):
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", access_log=False, ws="none"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 30
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                pytest.fail("The test FastAPI server did not start")
            time.sleep(.1)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        assert not thread.is_alive(), "The owned FastAPI server did not stop"


def test_browser_demo_against_api_and_local_chain(gold_snapshot, local_evm, tmp_path: Path):
    web = PROJECT_ROOT / "web"
    node = shutil.which("node")
    vite = web / "node_modules/vite/bin/vite.js"
    playwright = web / "node_modules/@playwright/test/cli.js"
    assert node and vite.is_file() and playwright.is_file(), "Run npm ci in web/ before browser tests"
    assert (web / "dist/index.html").is_file(), "Run npm run build in web/ before browser tests"
    settings, start, records, publish = gold_snapshot
    history = [replace(row, ts=start + timedelta(hours=hour), value=12.5 + (hour + 23) % 6,
                       residual=.5 + (hour + 23) % 6) for row in records[:3] for hour in range(-23, 0)]
    evidence = PlumeEvidence("b", start + timedelta(hours=1), 1, 1.1, .95, 8, 12)
    publish([replace(row, plume_evidence=(evidence,)) if row.station_id == "plume" else row for row in records] + history)
    # The first API-sorted station has no observations, as in the real catalog.
    # Initial Monitor selection must still open a station with actual readings.
    names = {"a": "Synthetic Central", "b": "Synthetic Riverside", "c": "Synthetic Gardens",
             "fault": "Synthetic Roadside", "plume": "Synthetic Downwind", "low": "Synthetic Sparse", "0": "Location only"}
    with duckdb.connect(str(settings.duckdb_path)) as db:
        db.execute("""CREATE SCHEMA silver;
            CREATE TABLE silver.stations(station_id TEXT, name TEXT, lat DOUBLE, lon DOUBLE, provider TEXT, cluster_id TEXT)""")
        db.executemany("INSERT INTO silver.stations VALUES (?,?,?,?,?,?)", [
            (station, name, 28.60 + index * .008, 77.20 + index * .01, "Synthetic browser fixture", "test")
            for index, (station, name) in enumerate(names.items())
        ])
    batches = prepare_batches(settings, start=start, end=start + timedelta(hours=2))
    w3, account = local_evm
    deployment = deploy_registry(w3, private_key=Web3.to_hex(account.key), chain_id=31337, journal=tmp_path / "browser-local.json")
    registry = Registry(w3, deployment["contract_address"], chain_id=31337)
    for batch in batches:
        submit_batch(settings, batch.batch_id, registry, private_key=Web3.to_hex(account.key))
    nonce = w3.eth.get_transaction_count(account.address)
    app = create_app(settings)
    app.dependency_overrides[get_registry_factory] = lambda: lambda: registry
    with api_server(app) as origin:
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = {key: value for key, value in os.environ.items() if not key.startswith("VITE_")
               and key not in {"PRIVATE_KEY", "RPC_URL", "OPENAQ_API_KEY", "REGISTRY_ADDRESS", "ECOPROOF_LOCAL_TEST_KEY", "FORCE_COLOR"}}
        env.update(ECOPROOF_API_ORIGIN=origin, ECOPROOF_BROWSER_BASE_URL=base_url, ECOPROOF_BROWSER_FIXTURE="synthetic", NO_COLOR="1")
        with (tmp_path / "vite.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen([node, str(vite), "preview", "--host", "127.0.0.1", "--port", str(port), "--strictPort"],
                cwd=web, env=env, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                deadline = time.monotonic() + 45
                with httpx.Client(trust_env=False, timeout=2) as client:
                    while True:
                        try:
                            if client.get(base_url).status_code == 200: break
                        except httpx.HTTPError:
                            pass
                        if process.poll() is not None or time.monotonic() > deadline:
                            pytest.fail("The test frontend server did not start; inspect its Vite log")
                        time.sleep(.2)
                result = subprocess.run([node, str(playwright), "test"], cwd=web, env=env, capture_output=True, text=True,
                                        encoding="utf-8", errors="replace", timeout=420)
                # Preserve exact UTF-8 output; Windows -s can otherwise fail to
                # print Playwright's checkmarks under a cp1252 console.
                (web / "test-results/browser-output.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
                print(result.stdout.encode("ascii", "backslashreplace").decode("ascii"))
                if result.stderr: print(result.stderr.encode("ascii", "backslashreplace").decode("ascii"))
                assert result.returncode == 0, "Browser checks failed; see Playwright output and web/test-results"
            finally:
                process.terminate()
                process.wait(timeout=15)
    assert w3.eth.get_transaction_count(account.address) == nonce, "The browser must only read chain state"
