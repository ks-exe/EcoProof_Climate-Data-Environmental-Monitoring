"""Immutable Bronze responses and bounded retries for the two data providers."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import math
import os
from pathlib import Path
import tempfile
import time
from typing import Any

import httpx


class IngestionError(RuntimeError):
    """A pull failed; messages must not include credentials or response bodies."""


@dataclass(frozen=True)
class Pull:
    path: Path
    response: dict[str, Any]
    from_cache: bool


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def validate_coordinates(latitude: float, longitude: float) -> None:
    if not (math.isfinite(latitude) and -90 <= latitude <= 90):
        raise ValueError("latitude must be finite and between -90 and 90")
    if not (math.isfinite(longitude) and -180 <= longitude <= 180):
        raise ValueError("longitude must be finite and between -180 and 180")


class CachedHTTP:
    """Cache successful JSON objects. Request metadata never includes headers."""

    def __init__(
        self,
        client: httpx.Client,
        bronze_dir: Path,
        *,
        max_attempts: int = 3,
        min_interval: float = 0.0,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        if not 1 <= max_attempts <= 5:
            raise ValueError("max_attempts must be between 1 and 5")
        if not math.isfinite(min_interval) or min_interval < 0:
            raise ValueError("min_interval must be finite and nonnegative")
        self.client = client
        self.bronze_dir = bronze_dir
        self.max_attempts = max_attempts
        self.min_interval = min_interval
        self._last_request: float | None = None
        self.sleep = sleep
        self.now = now

    def get(
        self,
        source: str,
        url: str,
        params: dict[str, str | int | float],
        *,
        context: dict[str, str | int] | None = None,
        headers: dict[str, str] | None = None,
        refresh: bool = False,
    ) -> Pull:
        if source not in ("openaq", "openmeteo"):
            raise ValueError("unsupported Bronze source")
        request = {"url": url, "params": params, "context": context or {}}
        if not refresh:
            for path in sorted(self.bronze_dir.glob(f"{source}_*.json"), reverse=True):
                try:
                    saved = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    raise IngestionError(f"Cannot read Bronze file {path.name}") from exc
                if not isinstance(saved, dict):
                    raise IngestionError(f"Invalid Bronze document in {path.name}")
                if saved.get("request") == request:
                    if not isinstance(saved.get("response"), dict):
                        raise IngestionError(f"Invalid Bronze response in {path.name}")
                    return Pull(path, saved["response"], True)
        response = self._request(source, url, params, headers)
        return self._save(source, request, response)

    def _request(
        self,
        source: str,
        url: str,
        params: dict[str, str | int | float],
        headers: dict[str, str] | None,
    ) -> dict[str, Any]:
        for attempt in range(self.max_attempts):
            response = None
            if self._last_request is not None:
                pause = self.min_interval - (time.monotonic() - self._last_request)
                if pause > 0:
                    self.sleep(pause)
            self._last_request = time.monotonic()
            try:
                response = self.client.get(
                    url, params=params, headers=headers, timeout=30.0,
                    follow_redirects=False,
                )
            except httpx.TransportError:
                failure = f"{source}: network request failed"
            else:
                if response.status_code == 200:
                    try:
                        payload = response.json()
                    except ValueError:
                        raise IngestionError(f"{source}: invalid JSON response") from None
                    if not isinstance(payload, dict) or payload.get("error") is True:
                        raise IngestionError(f"{source}: unexpected JSON response")
                    return payload
                failure = f"{source}: HTTP {response.status_code}"
                if response.status_code not in (408, 429, 500, 502, 503, 504):
                    raise IngestionError(failure)
            if attempt + 1 == self.max_attempts:
                raise IngestionError(f"{failure}; exhausted {self.max_attempts} attempts")
            delay = self._retry_delay(response, attempt)
            if delay > 60:
                raise IngestionError(f"{failure}; retry after {math.ceil(delay)} seconds")
            self.sleep(delay)
        raise AssertionError("unreachable")

    def _retry_delay(self, response: httpx.Response | None, attempt: int) -> float:
        backoff = float(2 ** attempt)
        if response is None:
            return backoff
        value = response.headers.get("retry-after")
        if value is not None:
            try:
                delay = float(value)
            except ValueError:
                try:
                    delay = (parsedate_to_datetime(value) - self.now()).total_seconds()
                except (TypeError, ValueError, OverflowError):
                    delay = math.nan
            if math.isfinite(delay):
                return max(backoff, delay)
        if response.status_code == 429:
            # OpenAQ examples use seconds; also accept an epoch reset timestamp.
            try:
                reset = float(response.headers.get("x-ratelimit-reset", "60"))
                delay = reset - self.now().timestamp() if reset > 1_000_000_000 else reset
                if math.isfinite(delay):
                    return max(backoff, delay)
            except ValueError:
                pass
            return 60.0
        return backoff

    def _save(
        self, source: str, request: dict[str, Any], response: dict[str, Any]
    ) -> Pull:
        fetched_at = self.now().astimezone(timezone.utc)
        envelope = {
            "schema_version": 1, "source": source,
            "fetched_at": fetched_at.isoformat().replace("+00:00", "Z"),
            "request": request, "response": response,
        }
        self.bronze_dir.mkdir(parents=True, exist_ok=True)
        # Publish a complete file using an exclusive hard link: no reader sees a
        # partial JSON document, and an existing Bronze file is never overwritten.
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.bronze_dir,
            prefix=".pending-", suffix=".tmp", delete=False,
        ) as file:
            temporary = Path(file.name)
            try:
                json.dump(envelope, file, ensure_ascii=False, allow_nan=False)
                file.flush()
                os.fsync(file.fileno())
            except BaseException:
                file.close()
                temporary.unlink()
                raise
        try:
            for offset in range(1000):
                stamp = (fetched_at + timedelta(microseconds=offset)).strftime("%Y%m%dT%H%M%S%fZ")
                path = self.bronze_dir / f"{source}_{stamp}.json"
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    continue
                return Pull(path, response, False)
            raise IngestionError("Could not allocate a unique Bronze filename")
        finally:
            temporary.unlink()
