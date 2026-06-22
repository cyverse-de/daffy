from __future__ import annotations

from collections.abc import Callable

from daffy.config import Config
from daffy.schema import LogRecord
from daffy.shipper import Shipper
from daffy.store import LogStore
from scrooge.server import ScroogeServer

ConfigFactory = Callable[..., Config]
RecordFactory = Callable[..., list[LogRecord]]


def test_flush_ships_batch_and_clears_local(
    scrooge: ScroogeServer, make_config: ConfigFactory, make_records: RecordFactory
) -> None:
    store = LogStore()
    store.insert_many(make_records(7))
    config = make_config(
        scrooge_uri=f"quack:127.0.0.1:{scrooge.config.quack_port}",
        scrooge_token="TESTTOKEN",
    )

    shipped = Shipper(config, store).flush()

    assert shipped == 7
    assert store.count() == 0
    remote = scrooge.conn.execute("SELECT count(*) FROM logs").fetchone()
    assert remote is not None and remote[0] == 7
    store.close()


def test_flush_retains_rows_when_scrooge_unreachable(
    make_config: ConfigFactory, make_records: RecordFactory
) -> None:
    store = LogStore()
    store.insert_many(make_records(5))
    config = make_config(scrooge_uri="quack:127.0.0.1:1", scrooge_token="x")

    shipped = Shipper(config, store).flush()

    assert shipped == 0
    assert store.count() == 5  # retained for retry, nothing deleted
    store.close()


def test_buffer_cap_drops_oldest_when_unreachable(
    make_config: ConfigFactory, make_records: RecordFactory
) -> None:
    store = LogStore()
    store.insert_many(make_records(20))
    config = make_config(
        scrooge_uri="quack:127.0.0.1:1",
        scrooge_token="x",
        max_buffer_rows=5,
    )

    Shipper(config, store).flush()

    assert store.count() == 5  # trimmed to the cap, oldest dropped
    store.close()


def test_shipping_disabled_is_noop(
    make_config: ConfigFactory, make_records: RecordFactory
) -> None:
    store = LogStore()
    store.insert_many(make_records(3))
    config = make_config()  # no scrooge_uri

    assert Shipper(config, store).flush() == 0
    assert store.count() == 3
    store.close()
