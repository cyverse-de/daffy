"""Canonical ``logs`` schema shared by the daffy buffer and the Scrooge store."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import duckdb

# Column order used by every INSERT/SELECT against the logs table.
COLUMNS: tuple[str, ...] = (
    "capture_time",
    "service",
    "pod",
    "node",
    "stream",
    "level",
    "message",
    "fields",
)

CREATE_LOGS_TABLE = """
CREATE TABLE IF NOT EXISTS logs (
    capture_time TIMESTAMP NOT NULL,
    service      VARCHAR    NOT NULL,
    pod          VARCHAR,
    node         VARCHAR,
    stream       VARCHAR    NOT NULL,
    level        VARCHAR    NOT NULL DEFAULT '',
    message      VARCHAR    NOT NULL,
    fields       JSON
)
"""


@dataclass(slots=True)
class LogRecord:
    """One captured log line."""

    capture_time: datetime
    service: str
    stream: str
    message: str
    level: str = ""
    pod: str | None = None
    node: str | None = None
    fields: str | None = None

    def as_row(self) -> tuple[object, ...]:
        """Return values in :data:`COLUMNS` order for parameterized inserts."""
        return (
            self.capture_time,
            self.service,
            self.pod,
            self.node,
            self.stream,
            self.level,
            self.message,
            self.fields,
        )


def ensure_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(CREATE_LOGS_TABLE)
