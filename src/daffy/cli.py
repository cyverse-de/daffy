"""``daffy`` entrypoint: wrap a process and capture its logs.

Usage: ``daffy [options] -- <command> [args...]``
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from daffy.config import (
    DEFAULT_FLUSH_BYTES,
    DEFAULT_FLUSH_INTERVAL,
    DEFAULT_LOCAL_DB,
    DEFAULT_MAX_BUFFER_BYTES,
    Config,
    build_config,
)
from daffy.shipper import Shipper
from daffy.store import LogStore
from daffy.wrapper import Wrapper


def _split_command(argv: Sequence[str]) -> tuple[list[str], list[str]]:
    argv = list(argv)
    if "--" in argv:
        idx = argv.index("--")
        return argv[:idx], argv[idx + 1 :]
    return argv, []


def _parse_args(args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="daffy",
        description="Wrap a process, teeing its stdout/stderr to the console and DuckDB.",
        epilog="Example: daffy --service my-svc -- my-server --port 8080",
    )
    parser.add_argument("--service", help="service name (or SERVICE_NAME; required)")
    parser.add_argument(
        "--local-db",
        help=f"local DuckDB buffer path (or DAFFY_LOCAL_DB; default: {DEFAULT_LOCAL_DB})",
    )
    parser.add_argument("--pod", help="Kubernetes pod name (or POD_NAME)")
    parser.add_argument("--node", help="Kubernetes node name (or NODE_NAME)")
    parser.add_argument(
        "--scrooge-uri",
        help="Scrooge quack URI, e.g. quack:host:9494 (or SCROOGE_URI; unset disables shipping)",
    )
    parser.add_argument("--scrooge-token", help="Scrooge auth token (prefer SCROOGE_TOKEN)")
    parser.add_argument(
        "--flush-bytes",
        type=int,
        help=f"flush when buffered bytes exceed this (or DAFFY_FLUSH_BYTES; default: {DEFAULT_FLUSH_BYTES})",
    )
    parser.add_argument(
        "--flush-interval",
        type=float,
        help=f"max seconds between flushes (or DAFFY_FLUSH_INTERVAL; default: {DEFAULT_FLUSH_INTERVAL})",
    )
    parser.add_argument(
        "--max-buffer-bytes",
        type=int,
        help=f"drop oldest beyond this when Scrooge is down (or DAFFY_MAX_BUFFER_BYTES; default: {DEFAULT_MAX_BUFFER_BYTES})",
    )
    return parser.parse_args(args)


def _config_from_args(ns: argparse.Namespace) -> Config:
    return build_config(
        service=ns.service,
        local_db=ns.local_db,
        pod=ns.pod,
        node=ns.node,
        scrooge_uri=ns.scrooge_uri,
        scrooge_token=ns.scrooge_token,
        flush_bytes=ns.flush_bytes,
        flush_interval=ns.flush_interval,
        max_buffer_bytes=ns.max_buffer_bytes,
    )


def main(argv: Sequence[str] | None = None) -> int:
    raw = sys.argv[1:] if argv is None else list(argv)
    daffy_args, command = _split_command(raw)
    ns = _parse_args(daffy_args)

    if not command:
        print("daffy: no command given; usage: daffy [options] -- <command>", file=sys.stderr)
        return 2

    try:
        config = _config_from_args(ns)
    except ValueError as err:
        print(f"daffy: {err}", file=sys.stderr)
        return 2

    store = LogStore(config.local_db)
    shipper = Shipper(config, store)
    try:
        shipper.start()
        returncode = Wrapper(config, store, on_records_written=shipper.maybe_flush).run(command)
    finally:
        shipper.close()
        store.close()

    # Translate a signal-terminated child (negative return code) to the shell convention.
    return 128 - returncode if returncode < 0 else returncode


if __name__ == "__main__":
    raise SystemExit(main())
