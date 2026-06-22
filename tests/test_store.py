from __future__ import annotations

from datetime import datetime

from daffy.schema import LogRecord
from daffy.store import LogStore


def _rec(message: str, **kw: object) -> LogRecord:
    return LogRecord(
        capture_time=datetime(2026, 6, 22, 12, 0, 0),
        service="demo",
        stream="stdout",
        message=message,
        **kw,  # type: ignore[arg-type]
    )


def test_insert_and_count() -> None:
    store = LogStore()
    store.insert_many([_rec("one"), _rec("two", level="error")])
    assert store.count() == 2
    store.close()


def test_insert_many_empty_is_noop() -> None:
    store = LogStore()
    store.insert_many([])
    assert store.count() == 0
    store.close()


def test_pending_bytes_tracks_messages() -> None:
    store = LogStore()
    assert store.pending_bytes() == 0
    store.insert_many([_rec("hello"), _rec("worldly")])
    assert store.pending_bytes() == len("hello") + len("worldly")
    store.close()


def test_round_trip_columns() -> None:
    store = LogStore()
    store.insert_many([_rec('{"level":"info"}', level="info", fields='{"level":"info"}')])
    with store.locked() as conn:
        row = conn.execute(
            "SELECT service, stream, level, message, fields FROM logs"
        ).fetchone()
    assert row == ("demo", "stdout", "info", '{"level":"info"}', '{"level":"info"}')
    store.close()
