"""Load local settings without opening data files or connecting to services."""

from dataclasses import dataclass, field
import os
from pathlib import Path

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    """Local data locations and optional server-side credentials."""

    data_dir: Path
    openaq_api_key: str | None = field(default=None, repr=False)
    rpc_url: str | None = field(default=None, repr=False)
    private_key: str | None = field(default=None, repr=False)
    registry_address: str | None = None

    @property
    def bronze_dir(self) -> Path:
        return self.data_dir / "bronze"

    @property
    def silver_dir(self) -> Path:
        return self.data_dir / "silver"

    @property
    def gold_dir(self) -> Path:
        return self.data_dir / "gold"

    @property
    def duckdb_path(self) -> Path:
        return self.data_dir / "ecoproof.duckdb"


def load_settings(project_root: Path = PROJECT_ROOT) -> Settings:
    """Read root .env, then environment overrides; relative paths use that root.

    Blank credentials become None. Values are literal (no ${...} interpolation),
    and loading settings does not mutate the process environment or create data.
    """
    root = project_root.resolve()
    values = {
        **dotenv_values(root / ".env", encoding="utf-8", interpolate=False),
        **os.environ,
    }
    data_dir = Path(values.get("ECOPROOF_DATA_DIR") or "data").expanduser()
    if not data_dir.is_absolute():
        data_dir = root / data_dir
    return Settings(
        data_dir=data_dir.resolve(),
        openaq_api_key=values.get("OPENAQ_API_KEY") or None,
        rpc_url=values.get("RPC_URL") or None,
        private_key=values.get("PRIVATE_KEY") or None,
        registry_address=values.get("REGISTRY_ADDRESS") or None,
    )
