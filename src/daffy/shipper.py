"""Batch-and-flush shipping of buffered logs to Scrooge over the Quack protocol.

The local buffer is bounded: lines accrue until a row-count threshold (or interval)
triggers a flush, which uploads the batch as one ``INSERT INTO scrooge.logs SELECT ...`` and then
deletes the flushed rows locally. The INSERT's success is the ack — nothing is deleted
until it succeeds, so the buffer survives Scrooge downtime. If Scrooge stays unreachable
and the buffer exceeds its cap, the oldest rows are dropped with a warning.
"""

from __future__ import annotations

import logging
import threading

import duckdb

from daffy.config import Config
from daffy.schema import COLUMNS
from daffy.sql import sql_literal
from daffy.store import LogStore, load_quack

log = logging.getLogger("daffy.shipper")

_COLS = ", ".join(COLUMNS)
_REMOTE = "scrooge"


def _quack_uri(uri: str) -> str:
    return uri if uri.startswith("quack:") else f"quack:{uri}"


class Shipper:
    def __init__(self, config: Config, store: LogStore) -> None:
        self._config = config
        self._store = store
        self._attached = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self._config.shipping_enabled:
            return
        self._thread = threading.Thread(target=self._loop, name="daffy-shipper", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._config.flush_interval + 5.0)
        self.flush()

    def maybe_flush(self) -> None:
        """Flush when the buffer has reached the row-count threshold."""
        if not self._config.shipping_enabled:
            return
        if self._store.count() >= self._config.flush_rows:
            self.flush()

    def flush(self) -> int:
        """Ship all currently-buffered rows as one batch; return rows shipped."""
        if not self._config.shipping_enabled:
            return 0
        with self._store.locked() as conn:
            if not self._ensure_attached(conn):
                self._enforce_cap(conn)
                return 0

            cutoff_row = conn.execute("SELECT max(capture_time) FROM logs").fetchone()
            cutoff = cutoff_row[0] if cutoff_row else None
            if cutoff is None:
                return 0

            count_row = conn.execute(
                "SELECT count(*) FROM logs WHERE capture_time <= ?", [cutoff]
            ).fetchone()
            pending = int(count_row[0]) if count_row else 0
            if pending == 0:
                return 0

            try:
                conn.execute(
                    f"INSERT INTO {_REMOTE}.logs ({_COLS}) "
                    f"SELECT {_COLS} FROM logs WHERE capture_time <= ?",
                    [cutoff],
                )
            except duckdb.Error as err:
                log.warning(
                    "flush to scrooge failed (%s); retaining %d rows to retry — "
                    "probable cause: Scrooge unreachable or token rejected",
                    err,
                    pending,
                )
                self._attached = False
                self._enforce_cap(conn)
                return 0

            conn.execute("DELETE FROM logs WHERE capture_time <= ?", [cutoff])
            return pending

    def _loop(self) -> None:
        while not self._stop.wait(self._config.flush_interval):
            try:
                self.flush()
            except duckdb.Error as err:
                log.warning("periodic flush error: %s", err)

    def _ensure_attached(self, conn: duckdb.DuckDBPyConnection) -> bool:
        if self._attached:
            return True
        assert self._config.scrooge_uri is not None
        uri = _quack_uri(self._config.scrooge_uri)
        attach = f"ATTACH {sql_literal(uri)} AS {_REMOTE}"
        if self._config.scrooge_token:
            attach += f" (TOKEN {sql_literal(self._config.scrooge_token)})"
        try:
            load_quack(conn)
            try:
                conn.execute(f"DETACH {_REMOTE}")
            except duckdb.Error:
                pass
            conn.execute(attach)
        except duckdb.Error as err:
            log.warning("cannot attach scrooge at %s: %s", uri, err)
            return False
        self._attached = True
        return True

    def _enforce_cap(self, conn: duckdb.DuckDBPyConnection) -> None:
        excess = self._count(conn) - self._config.max_buffer_rows
        if excess <= 0:
            return
        conn.execute(
            "DELETE FROM logs WHERE rowid IN "
            "(SELECT rowid FROM logs ORDER BY capture_time LIMIT ?)",
            [excess],
        )
        log.warning(
            "dropped %d oldest buffered rows to stay under %d rows — "
            "probable cause: Scrooge unreachable, buffer cap hit",
            excess,
            self._config.max_buffer_rows,
        )

    @staticmethod
    def _count(conn: duckdb.DuckDBPyConnection) -> int:
        row = conn.execute("SELECT count(*) FROM logs").fetchone()
        return int(row[0]) if row else 0
