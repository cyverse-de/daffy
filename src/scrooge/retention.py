"""Roll older logs out of the live DuckDB into per-service, per-day Parquet files.

When a service's live row count exceeds the threshold, the oldest log-days are exported
(oldest first) and deleted until the service is back under the threshold. The most recent
day is kept live when possible so recent logs stay queryable without touching Parquet.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

from daffy.schema import COLUMNS
from daffy.sql import sql_literal

_SELECT_COLS = ", ".join(COLUMNS)


def service_dir(storage_dir: str | Path, service: str) -> Path:
    return Path(storage_dir) / service.lower()


def _next_sequence(directory: Path, day: str, service_lower: str) -> int:
    suffix = f"_{service_lower}.parquet"
    highest = 0
    for path in directory.glob(f"{day}-*{suffix}"):
        seq_part = path.name[len(day) + 1 : -len(suffix)]
        if seq_part.isdigit():
            highest = max(highest, int(seq_part))
    return highest + 1


def export_day(conn: duckdb.DuckDBPyConnection, storage_dir: str | Path, service: str, day: date) -> Path:
    """Export one service's logs for one day to a new Parquet file and return its path."""
    directory = service_dir(storage_dir, service)
    directory.mkdir(parents=True, exist_ok=True)
    day_str = day.isoformat()
    service_lower = service.lower()
    seq = _next_sequence(directory, day_str, service_lower)
    out_path = directory / f"{day_str}-{seq:03d}_{service_lower}.parquet"

    predicate = f"service = {sql_literal(service)} AND capture_time::date = DATE {sql_literal(day_str)}"
    conn.execute(
        f"COPY (SELECT {_SELECT_COLS} FROM logs WHERE {predicate} ORDER BY capture_time) "
        f"TO {sql_literal(str(out_path))} (FORMAT PARQUET)"
    )
    conn.execute(f"DELETE FROM logs WHERE {predicate}")
    return out_path


def _service_count(conn: duckdb.DuckDBPyConnection, service: str) -> int:
    row = conn.execute("SELECT count(*) FROM logs WHERE service = ?", [service]).fetchone()
    return int(row[0]) if row else 0


def _days_for_service(conn: duckdb.DuckDBPyConnection, service: str) -> list[date]:
    rows = conn.execute(
        "SELECT DISTINCT capture_time::date AS d FROM logs WHERE service = ? ORDER BY d",
        [service],
    ).fetchall()
    return [r[0] for r in rows]


def sweep_once(conn: duckdb.DuckDBPyConnection, storage_dir: str | Path, threshold: int) -> list[Path]:
    """Export and delete oldest log-days for every over-threshold service.

    Returns the list of Parquet files written.
    """
    services = [
        r[0]
        for r in conn.execute(
            "SELECT service FROM logs GROUP BY service HAVING count(*) > ?",
            [threshold],
        ).fetchall()
    ]

    written: list[Path] = []
    for service in services:
        while _service_count(conn, service) > threshold:
            days = _days_for_service(conn, service)
            if not days:
                break
            written.append(export_day(conn, storage_dir, service, days[0]))
    return written
