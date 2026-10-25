"""Offline checks for configuration boundaries and secret handling."""

import os
from pathlib import Path

import pytest

from ecoproof.config import load_settings


@pytest.fixture(autouse=True)
def isolated_config_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPENAQ_API_KEY", "RPC_URL", "PRIVATE_KEY", "ECOPROOF_DATA_DIR", "REGISTRY_ADDRESS"):
        monkeypatch.delenv(name, raising=False)


def test_defaults_need_no_credentials_and_do_not_create_data(tmp_path: Path) -> None:
    settings = load_settings(tmp_path)

    assert settings.data_dir == tmp_path / "data"
    assert settings.bronze_dir == tmp_path / "data" / "bronze"
    assert settings.silver_dir == tmp_path / "data" / "silver"
    assert settings.gold_dir == tmp_path / "data" / "gold"
    assert settings.duckdb_path == tmp_path / "data" / "ecoproof.duckdb"
    assert settings.openaq_api_key is None
    assert settings.rpc_url is None
    assert settings.private_key is None
    assert settings.registry_address is None
    assert not settings.data_dir.exists()


def test_registry_address_reads_file_and_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("REGISTRY_ADDRESS=file-address\n", encoding="utf-8")
    assert load_settings(tmp_path).registry_address == "file-address"
    monkeypatch.setenv("REGISTRY_ADDRESS", "env-address")
    assert load_settings(tmp_path).registry_address == "env-address"
    monkeypatch.setenv("REGISTRY_ADDRESS", "")
    assert load_settings(tmp_path).registry_address is None


def test_dotenv_loads_without_mutating_environment(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "OPENAQ_API_KEY=test-file-key\n"
        "RPC_URL=https://rpc.invalid/test-only\n"
        "PRIVATE_KEY=test-private-key-not-a-wallet\n"
        "ECOPROOF_DATA_DIR=local data\n",
        encoding="utf-8",
    )
    before = dict(os.environ)

    settings = load_settings(tmp_path)

    assert settings.openaq_api_key == "test-file-key"
    assert settings.rpc_url == "https://rpc.invalid/test-only"
    assert settings.private_key == "test-private-key-not-a-wallet"
    assert settings.data_dir == tmp_path / "local data"
    assert dict(os.environ) == before


def test_environment_overrides_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text(
        "OPENAQ_API_KEY=file-value\nPRIVATE_KEY=file-value\n"
        "RPC_URL=file-value\nECOPROOF_DATA_DIR=file-data\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAQ_API_KEY", "env-key")
    monkeypatch.setenv("RPC_URL", "https://rpc.invalid/env-only")
    monkeypatch.setenv("PRIVATE_KEY", "env-private-key-not-a-wallet")
    monkeypatch.setenv("ECOPROOF_DATA_DIR", "env-data")

    settings = load_settings(tmp_path)

    assert settings.openaq_api_key == "env-key"
    assert settings.rpc_url == "https://rpc.invalid/env-only"
    assert settings.private_key == "env-private-key-not-a-wallet"
    assert settings.data_dir == tmp_path / "env-data"


def test_blank_environment_clears_file_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text(
        "OPENAQ_API_KEY=file-value\nPRIVATE_KEY=file-value\nRPC_URL=file-value\n",
        encoding="utf-8",
    )
    for name in ("OPENAQ_API_KEY", "RPC_URL", "PRIVATE_KEY", "ECOPROOF_DATA_DIR"):
        monkeypatch.setenv(name, "")

    settings = load_settings(tmp_path)

    assert settings.openaq_api_key is None
    assert settings.private_key is None
    assert settings.rpc_url is None
    assert settings.data_dir == tmp_path / "data"


def test_relative_data_path_is_independent_of_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (project / ".env").write_text("ECOPROOF_DATA_DIR=local data\n", encoding="utf-8")
    monkeypatch.chdir(elsewhere)

    assert load_settings(project).data_dir == project / "local data"


def test_absolute_data_path_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    location = tmp_path / "external data"
    monkeypatch.setenv("ECOPROOF_DATA_DIR", str(location))

    assert load_settings(tmp_path / "project").data_dir == location


def test_credentials_are_literal_and_not_in_repr(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "OPENAQ_API_KEY=test-${PRIVATE_KEY}\n"
        "PRIVATE_KEY=never-a-real-wallet\n"
        "RPC_URL=https://rpc.invalid/private-token\n",
        encoding="utf-8",
    )

    settings = load_settings(tmp_path)

    assert settings.openaq_api_key == "test-${PRIVATE_KEY}"
    for value in (settings.openaq_api_key, settings.private_key, settings.rpc_url):
        assert value is not None
        assert value not in repr(settings)
