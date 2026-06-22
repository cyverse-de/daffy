"""``scrooge`` entrypoint: run the log aggregator and Quack server."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from collections.abc import Sequence

from scrooge.config import (
    DEFAULT_DB_PATH,
    DEFAULT_QUACK_HOST,
    DEFAULT_QUACK_PORT,
    DEFAULT_RETENTION_ROWS,
    DEFAULT_STORAGE_DIR,
    DEFAULT_SWEEP_INTERVAL,
    ScroogeConfig,
    build_config,
)
from scrooge.server import ScroogeServer

log = logging.getLogger("scrooge")


def _parse_args(args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scrooge",
        description="Aggregate logs shipped by daffy instances; archive older logs to Parquet.",
    )
    parser.add_argument(
        "--db",
        dest="db_path",
        help=f"aggregator DuckDB path (or SCROOGE_DB; default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--storage-dir",
        help=f"Parquet archive root (or SCROOGE_STORAGE_DIR; default: {DEFAULT_STORAGE_DIR})",
    )
    parser.add_argument(
        "--quack-host",
        help=f"Quack bind host (or SCROOGE_QUACK_HOST; default: {DEFAULT_QUACK_HOST})",
    )
    parser.add_argument(
        "--quack-port",
        type=int,
        help=f"Quack bind port (or SCROOGE_QUACK_PORT; default: {DEFAULT_QUACK_PORT})",
    )
    parser.add_argument(
        "--token",
        help="fixed Quack auth token (prefer SCROOGE_TOKEN; default: random per boot)",
    )
    parser.add_argument(
        "--retention-rows",
        type=int,
        help=f"per-service live row threshold (or SCROOGE_RETENTION_ROWS; default: {DEFAULT_RETENTION_ROWS})",
    )
    parser.add_argument(
        "--sweep-interval",
        type=float,
        help=f"seconds between retention sweeps (or SCROOGE_SWEEP_INTERVAL; default: {DEFAULT_SWEEP_INTERVAL})",
    )
    return parser.parse_args(args)


def _config_from_args(ns: argparse.Namespace) -> ScroogeConfig:
    return build_config(
        db_path=ns.db_path,
        storage_dir=ns.storage_dir,
        quack_host=ns.quack_host,
        quack_port=ns.quack_port,
        token=ns.token,
        retention_rows=ns.retention_rows,
        sweep_interval=ns.sweep_interval,
    )


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ns = _parse_args(sys.argv[1:] if argv is None else list(argv))
    config = _config_from_args(ns)

    server = ScroogeServer(config)
    shutdown = threading.Event()

    def _stop(_signum: int, _frame: object) -> None:
        shutdown.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    server.start()
    try:
        while not shutdown.wait(timeout=config.sweep_interval):
            server.sweep()
    finally:
        server.sweep()
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
