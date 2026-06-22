from __future__ import annotations

import logging
from collections.abc import Callable

import pytest

from daffy.config import Config
from daffy.schema import LogRecord
from daffy.shipper import Shipper
from daffy.store import LogStore
from scrooge.monitor import QuackLogMonitor
from scrooge.server import ScroogeServer

ConfigFactory = Callable[..., Config]
RecordFactory = Callable[..., list[LogRecord]]


def _ship(scrooge: ScroogeServer, make_config: ConfigFactory, records: list[LogRecord]) -> None:
    store = LogStore()
    store.insert_many(records)
    config = make_config(
        scrooge_uri=f"quack:127.0.0.1:{scrooge.config.quack_port}",
        scrooge_token="TESTTOKEN",
    )
    Shipper(config, store).flush()
    store.close()


def test_drain_reports_connection_and_upload(
    scrooge: ScroogeServer, make_config: ConfigFactory, make_records: RecordFactory
) -> None:
    _ship(scrooge, make_config, make_records(5))

    types = [row[0] for row in scrooge.drain_quack_log()]

    assert "CONNECTION_REQUEST" in types
    assert "APPEND_REQUEST" in types


def test_drain_clears_buffer(
    scrooge: ScroogeServer, make_config: ConfigFactory, make_records: RecordFactory
) -> None:
    _ship(scrooge, make_config, make_records(3))
    assert scrooge.drain_quack_log()  # first drain returns rows
    assert scrooge.drain_quack_log() == []  # buffer was truncated


def test_monitor_logs_upload(
    scrooge: ScroogeServer,
    make_config: ConfigFactory,
    make_records: RecordFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _ship(scrooge, make_config, make_records(4))

    monitor = QuackLogMonitor(scrooge, interval=60.0)  # long interval; we drive _drain directly
    with caplog.at_level(logging.INFO, logger="scrooge.monitor"):
        monitor._drain()

    assert "daffy connected" in caplog.text
    assert "upload received" in caplog.text
