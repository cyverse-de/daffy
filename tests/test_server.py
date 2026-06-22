from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from daffy.schema import COLUMNS
from scrooge.config import build_config
from scrooge.server import ScroogeServer


@pytest.fixture
def server(tmp_path: Path) -> Iterator[ScroogeServer]:
    config = build_config(
        db_path=str(tmp_path / "scrooge.duckdb"),
        storage_dir=str(tmp_path / "archive"),
        quack_port=0,  # not started in these tests
        retention_rows=5,
    )
    srv = ScroogeServer(config)
    yield srv
    srv.conn.close()


def _insert(server: ScroogeServer, day: int, n: int) -> None:
    server.conn.execute(
        f"INSERT INTO logs ({', '.join(COLUMNS)}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [datetime(2026, 6, day, 0, 0, n), "svc", None, None, "stdout", "", f"m{day}-{n}", None],
    )


def test_all_logs_empty_archive_is_valid(server: ScroogeServer) -> None:
    server.refresh_view()
    _insert(server, 22, 0)
    assert server.conn.execute("SELECT count(*) FROM all_logs").fetchone()[0] == 1  # type: ignore[index]


def test_all_logs_spans_live_and_parquet(server: ScroogeServer) -> None:
    for n in range(10):
        _insert(server, 21, n)
    for n in range(3):
        _insert(server, 22, n)

    written = server.sweep()  # rolls the over-threshold oldest day to parquet
    assert written

    total = server.conn.execute("SELECT count(*) FROM all_logs").fetchone()[0]  # type: ignore[index]
    assert total == 13  # 10 archived + 3 live, unified

    live = server.conn.execute("SELECT count(*) FROM logs").fetchone()[0]  # type: ignore[index]
    assert live == 3
