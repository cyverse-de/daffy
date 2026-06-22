"""Scrooge's DuckDB instance: the Quack server, the unified query view, and sweeps."""

from __future__ import annotations

import glob
import logging
from pathlib import Path

import duckdb

from daffy.schema import COLUMNS, ensure_schema
from daffy.store import load_quack
from scrooge import retention
from scrooge.config import ScroogeConfig

log = logging.getLogger("scrooge")

_SELECT_COLS = ", ".join(COLUMNS)


def _sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class ScroogeServer:
    """Owns the aggregator DuckDB connection and the Quack endpoint."""

    def __init__(self, config: ScroogeConfig) -> None:
        self.config = config
        self.conn = duckdb.connect(config.db_path)
        load_quack(self.conn)
        ensure_schema(self.conn)
        self.token: str | None = None

    def start(self) -> None:
        Path(self.config.storage_dir).mkdir(parents=True, exist_ok=True)
        call = f"CALL quack_serve({_sql_str(self.config.listen_uri)}, allow_other_hostname => true"
        if self.config.token:
            call += f", token => {_sql_str(self.config.token)}"
        call += ")"
        row = self.conn.execute(call).fetchone()
        # quack_serve returns (listen_uri, http_url, auth_token)
        self.token = row[2] if row else None
        self.refresh_view()
        log.info("scrooge serving on %s", self.config.listen_uri)

    def refresh_view(self) -> None:
        """(Re)create the ``all_logs`` view spanning live rows and the Parquet archive."""
        pattern = str(Path(self.config.storage_dir).resolve() / "*" / "*.parquet")
        if glob.glob(pattern):
            sql = (
                f"CREATE OR REPLACE VIEW all_logs AS "
                f"SELECT {_SELECT_COLS} FROM logs "
                f"UNION ALL "
                f"SELECT {_SELECT_COLS} FROM read_parquet({_sql_str(pattern)}, union_by_name => true)"
            )
        else:
            sql = f"CREATE OR REPLACE VIEW all_logs AS SELECT {_SELECT_COLS} FROM logs"
        self.conn.execute(sql)

    def sweep(self) -> list[Path]:
        written = retention.sweep_once(self.conn, self.config.storage_dir, self.config.retention_rows)
        if written:
            self.refresh_view()
            log.info("rolled %d parquet file(s) to %s", len(written), self.config.storage_dir)
        return written

    def stop(self) -> None:
        try:
            self.conn.execute(f"CALL quack_stop({_sql_str(self.config.listen_uri)})")
        except duckdb.Error:
            pass
        self.conn.close()
