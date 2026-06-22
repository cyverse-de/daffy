from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
import pytest

from daffy.schema import COLUMNS, ensure_schema
from scrooge import retention


def _conn_with_rows(rows: list[tuple[object, ...]]) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    ensure_schema(conn)
    placeholders = ", ".join("?" for _ in COLUMNS)
    conn.executemany(
        f"INSERT INTO logs ({', '.join(COLUMNS)}) VALUES ({placeholders})", rows
    )
    return conn


def _row(day: int, n: int, service: str = "svc") -> tuple[object, ...]:
    return (
        datetime(2026, 6, day, 0, 0, 0, n),
        service,
        None,
        None,
        "stdout",
        "",
        f"msg-{day}-{n}",
        None,
    )


def test_sweep_exports_oldest_days_until_under_threshold(tmp_path: Path) -> None:
    rows = [_row(21, n) for n in range(10)] + [_row(22, n) for n in range(10)]
    conn = _conn_with_rows(rows)

    written = retention.sweep_once(conn, tmp_path, threshold=5)

    names = sorted(p.name for p in written)
    assert names == ["2026-06-21-001_svc.parquet", "2026-06-22-001_svc.parquet"]
    for p in written:
        assert p.exists()
    assert conn.execute("SELECT count(*) FROM logs").fetchone()[0] == 0  # type: ignore[index]


def test_sweep_keeps_recent_day_when_under_threshold(tmp_path: Path) -> None:
    rows = [_row(21, n) for n in range(10)] + [_row(22, n) for n in range(4)]
    conn = _conn_with_rows(rows)

    written = retention.sweep_once(conn, tmp_path, threshold=5)

    assert [p.name for p in written] == ["2026-06-21-001_svc.parquet"]
    remaining = conn.execute("SELECT count(*) FROM logs").fetchone()[0]  # type: ignore[index]
    assert remaining == 4


def test_sequence_increments_for_same_day(tmp_path: Path) -> None:
    conn = _conn_with_rows([_row(21, n) for n in range(3)])
    first = retention.export_day(conn, tmp_path, "svc", datetime(2026, 6, 21).date())
    conn.executemany(
        f"INSERT INTO logs ({', '.join(COLUMNS)}) VALUES ({', '.join('?' for _ in COLUMNS)})",
        [_row(21, 99)],
    )
    second = retention.export_day(conn, tmp_path, "svc", datetime(2026, 6, 21).date())
    assert first.name == "2026-06-21-001_svc.parquet"
    assert second.name == "2026-06-21-002_svc.parquet"


def test_service_name_lowercased_in_path(tmp_path: Path) -> None:
    conn = _conn_with_rows([_row(21, n, service="My-Service") for n in range(3)])
    out = retention.export_day(conn, tmp_path, "My-Service", datetime(2026, 6, 21).date())
    assert out.parent.name == "my-service"
    assert out.name == "2026-06-21-001_my-service.parquet"


@pytest.mark.parametrize("threshold", [0, 100])
def test_sweep_threshold_boundaries(tmp_path: Path, threshold: int) -> None:
    conn = _conn_with_rows([_row(21, n) for n in range(10)])
    written = retention.sweep_once(conn, tmp_path, threshold=threshold)
    if threshold >= 10:
        assert written == []
    else:
        assert written  # something was rolled out
