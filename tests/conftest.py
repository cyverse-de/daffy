from __future__ import annotations

import socket
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

import pytest

from daffy.config import Config, build_config
from daffy.schema import LogRecord
from scrooge.config import build_config as build_scrooge_config
from scrooge.server import ScroogeServer

ConfigFactory = Callable[..., Config]
TEST_TOKEN = "TESTTOKEN"


@pytest.fixture
def make_config() -> ConfigFactory:
    def _make(service: str = "demo", local_db: str = ":memory:", **overrides: object) -> Config:
        kwargs: dict[str, object] = {
            "service": service,
            "local_db": local_db,
            "pod": None,
            "node": None,
            "scrooge_uri": None,
            "scrooge_token": None,
            "flush_rows": None,
            "flush_interval": None,
            "max_buffer_rows": None,
        }
        kwargs.update(overrides)
        return build_config(**kwargs)  # type: ignore[arg-type]

    return _make


@pytest.fixture
def make_records() -> Callable[..., list[LogRecord]]:
    def _make(n: int, message: str = "hello", service: str = "demo") -> list[LogRecord]:
        return [
            LogRecord(
                capture_time=datetime(2026, 6, 22, 0, 0, 0, i),
                service=service,
                stream="stdout",
                message=f"{message}-{i}",
            )
            for i in range(n)
        ]

    return _make


@pytest.fixture
def free_port() -> Callable[[], int]:
    def _free() -> int:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    return _free


@pytest.fixture
def scrooge(tmp_path: Path, free_port: Callable[[], int]) -> Iterator[ScroogeServer]:
    config = build_scrooge_config(
        db_path=str(tmp_path / "scrooge.duckdb"),
        storage_dir=str(tmp_path / "archive"),
        quack_host="127.0.0.1",
        quack_port=free_port(),
        token=TEST_TOKEN,
    )
    server = ScroogeServer(config)
    server.start()
    yield server
    server.stop()
