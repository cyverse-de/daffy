"""Local DuckDB buffer for captured log lines.

The buffer is intentionally bounded: lines accrue here until the shipper flushes them to
Scrooge, after which they are deleted locally. All access is serialized through a single
connection guarded by a lock (DuckDB connections are not safe for concurrent use).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import duckdb

from daffy.schema import COLUMNS, LogRecord, ensure_schema

_INSERT_SQL = (
    f"INSERT INTO logs ({', '.join(COLUMNS)}) "
    f"VALUES ({', '.join('?' for _ in COLUMNS)})"
)


def load_quack(conn: duckdb.DuckDBPyConnection) -> None:
    """Load the Quack extension, installing it first if it isn't bundled."""
    try:
        conn.execute("LOAD quack")
    except duckdb.Error:
        conn.execute("INSTALL quack")
        conn.execute("LOAD quack")


class LogStore:
    """A thread-safe local DuckDB log buffer."""

    def __init__(self, path: str = ":memory:") -> None:
        self._lock = threading.Lock()
        self._conn = duckdb.connect(path)
        ensure_schema(self._conn)

    @contextmanager
    def locked(self) -> Iterator[duckdb.DuckDBPyConnection]:
        """Yield the underlying connection while holding the buffer lock.

        Used by the shipper to run multi-statement, cross-catalog operations (ATTACH +
        ``INSERT INTO scrooge.logs SELECT ... FROM logs`` + ``DELETE``) atomically.
        """
        with self._lock:
            yield self._conn

    def insert_many(self, records: Sequence[LogRecord]) -> None:
        if not records:
            return
        rows = [r.as_row() for r in records]
        with self._lock:
            self._conn.executemany(_INSERT_SQL, rows)

    def count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT count(*) FROM logs").fetchone()
        return int(row[0]) if row else 0

    def close(self) -> None:
        with self._lock:
            self._conn.close()
