"""Scrooge configuration, resolved env-first with CLI-flag fallback."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_STORAGE_DIR = "./scrooge"
DEFAULT_DB_PATH = "scrooge.duckdb"
DEFAULT_QUACK_HOST = "0.0.0.0"
DEFAULT_QUACK_PORT = 9494
DEFAULT_RETENTION_ROWS = 100_000
DEFAULT_SWEEP_INTERVAL = 10.0


@dataclass(slots=True)
class ScroogeConfig:
    db_path: str
    storage_dir: str
    quack_host: str
    quack_port: int
    token: str | None
    retention_rows: int
    sweep_interval: float

    @property
    def listen_uri(self) -> str:
        return f"quack:{self.quack_host}:{self.quack_port}"


def _resolve(env_name: str, flag: str | None, default: str | None) -> str | None:
    return os.environ.get(env_name) or flag or default


def _resolve_int(env_name: str, flag: int | None, default: int) -> int:
    env_value = os.environ.get(env_name)
    if env_value is not None:
        return int(env_value)
    return flag if flag is not None else default


def _resolve_float(env_name: str, flag: float | None, default: float) -> float:
    env_value = os.environ.get(env_name)
    if env_value is not None:
        return float(env_value)
    return flag if flag is not None else default


def build_config(
    *,
    db_path: str | None = None,
    storage_dir: str | None = None,
    quack_host: str | None = None,
    quack_port: int | None = None,
    token: str | None = None,
    retention_rows: int | None = None,
    sweep_interval: float | None = None,
) -> ScroogeConfig:
    return ScroogeConfig(
        db_path=_resolve("SCROOGE_DB", db_path, DEFAULT_DB_PATH) or DEFAULT_DB_PATH,
        storage_dir=_resolve("SCROOGE_STORAGE_DIR", storage_dir, DEFAULT_STORAGE_DIR)
        or DEFAULT_STORAGE_DIR,
        quack_host=_resolve("SCROOGE_QUACK_HOST", quack_host, DEFAULT_QUACK_HOST)
        or DEFAULT_QUACK_HOST,
        quack_port=_resolve_int("SCROOGE_QUACK_PORT", quack_port, DEFAULT_QUACK_PORT),
        token=_resolve("SCROOGE_TOKEN", token, None),
        retention_rows=_resolve_int("SCROOGE_RETENTION_ROWS", retention_rows, DEFAULT_RETENTION_ROWS),
        sweep_interval=_resolve_float("SCROOGE_SWEEP_INTERVAL", sweep_interval, DEFAULT_SWEEP_INTERVAL),
    )
