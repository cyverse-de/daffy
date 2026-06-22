"""daffy configuration, resolved env-first with CLI-flag fallback.

Env wins over flags so secrets (the Scrooge token) can be supplied via the environment
without appearing in ``ps aux``; non-secret settings follow the same rule for consistency.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_LOCAL_DB = ":memory:"
DEFAULT_FLUSH_ROWS = 1_000
DEFAULT_FLUSH_INTERVAL = 5.0
DEFAULT_MAX_BUFFER_ROWS = 100_000


def _resolve(env_name: str, flag_value: str | None, default: str | None = None) -> str | None:
    env_value = os.environ.get(env_name)
    if env_value is not None:
        return env_value
    if flag_value is not None:
        return flag_value
    return default


def _resolve_int(env_name: str, flag_value: int | None, default: int) -> int:
    env_value = os.environ.get(env_name)
    if env_value is not None:
        return int(env_value)
    if flag_value is not None:
        return flag_value
    return default


def _resolve_float(env_name: str, flag_value: float | None, default: float) -> float:
    env_value = os.environ.get(env_name)
    if env_value is not None:
        return float(env_value)
    if flag_value is not None:
        return flag_value
    return default


@dataclass(slots=True)
class Config:
    service: str
    local_db: str
    pod: str | None
    node: str | None
    scrooge_uri: str | None
    scrooge_token: str | None
    flush_rows: int
    flush_interval: float
    max_buffer_rows: int

    @property
    def shipping_enabled(self) -> bool:
        return bool(self.scrooge_uri)


def build_config(
    *,
    service: str | None,
    local_db: str | None,
    pod: str | None,
    node: str | None,
    scrooge_uri: str | None,
    scrooge_token: str | None,
    flush_rows: int | None,
    flush_interval: float | None,
    max_buffer_rows: int | None,
) -> Config:
    resolved_service = _resolve("SERVICE_NAME", service)
    if not resolved_service:
        raise ValueError("a service name is required (set --service or SERVICE_NAME)")

    return Config(
        service=resolved_service,
        local_db=_resolve("DAFFY_LOCAL_DB", local_db, DEFAULT_LOCAL_DB) or DEFAULT_LOCAL_DB,
        pod=_resolve("POD_NAME", pod),
        node=_resolve("NODE_NAME", node),
        scrooge_uri=_resolve("SCROOGE_URI", scrooge_uri),
        scrooge_token=_resolve("SCROOGE_TOKEN", scrooge_token),
        flush_rows=_resolve_int("DAFFY_FLUSH_ROWS", flush_rows, DEFAULT_FLUSH_ROWS),
        flush_interval=_resolve_float(
            "DAFFY_FLUSH_INTERVAL", flush_interval, DEFAULT_FLUSH_INTERVAL
        ),
        max_buffer_rows=_resolve_int(
            "DAFFY_MAX_BUFFER_ROWS", max_buffer_rows, DEFAULT_MAX_BUFFER_ROWS
        ),
    )
