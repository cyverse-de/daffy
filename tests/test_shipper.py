from __future__ import annotations

import socket
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

import pytest

from daffy.config import Config
from daffy.schema import LogRecord
from daffy.shipper import Shipper
from daffy.store import LogStore
from scrooge.config import build_config as build_scrooge_config
from scrooge.server import ScroogeServer

ConfigFactory = Callable[..., Config]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _records(n: int, message: str = "hello") -> list[LogRecord]:
    return [
        LogRecord(
            capture_time=datetime(2026, 6, 22, 0, 0, 0, i),
            service="demo",
            stream="stdout",
            message=f"{message}-{i}",
        )
        for i in range(n)
    ]


@pytest.fixture
def scrooge(tmp_path: Path) -> Iterator[ScroogeServer]:
    config = build_scrooge_config(
        db_path=str(tmp_path / "scrooge.duckdb"),
        storage_dir=str(tmp_path / "archive"),
        quack_host="127.0.0.1",
        quack_port=_free_port(),
        token="TESTTOKEN",
    )
    server = ScroogeServer(config)
    server.start()
    yield server
    server.stop()


def test_flush_ships_batch_and_clears_local(scrooge: ScroogeServer, make_config: ConfigFactory) -> None:
    store = LogStore()
    store.insert_many(_records(7))
    config = make_config(
        scrooge_uri=f"quack:127.0.0.1:{scrooge.config.quack_port}",
        scrooge_token="TESTTOKEN",
    )

    shipped = Shipper(config, store).flush()

    assert shipped == 7
    assert store.count() == 0
    remote = scrooge.conn.execute("SELECT count(*) FROM logs").fetchone()
    assert remote is not None and remote[0] == 7
    store.close()


def test_flush_retains_rows_when_scrooge_unreachable(make_config: ConfigFactory) -> None:
    store = LogStore()
    store.insert_many(_records(5))
    config = make_config(scrooge_uri="quack:127.0.0.1:1", scrooge_token="x")

    shipped = Shipper(config, store).flush()

    assert shipped == 0
    assert store.count() == 5  # retained for retry, nothing deleted
    store.close()


def test_buffer_cap_drops_oldest_when_unreachable(make_config: ConfigFactory) -> None:
    store = LogStore()
    store.insert_many(_records(20))
    config = make_config(
        scrooge_uri="quack:127.0.0.1:1",
        scrooge_token="x",
        max_buffer_rows=5,
    )

    Shipper(config, store).flush()

    assert store.count() == 5  # trimmed to the cap, oldest dropped
    store.close()


def test_shipping_disabled_is_noop(make_config: ConfigFactory) -> None:
    store = LogStore()
    store.insert_many(_records(3))
    config = make_config()  # no scrooge_uri

    assert Shipper(config, store).flush() == 0
    assert store.count() == 3
    store.close()
