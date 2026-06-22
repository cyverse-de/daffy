from __future__ import annotations

from collections.abc import Callable

import pytest

from daffy.config import Config
from daffy.store import LogStore
from daffy.wrapper import Wrapper

ConfigFactory = Callable[..., Config]


def test_captures_both_streams_to_console_and_store(
    capfd: pytest.CaptureFixture[str], make_config: ConfigFactory
) -> None:
    store = LogStore()
    rc = Wrapper(make_config(), store).run(["sh", "-c", "echo out; echo err 1>&2"])
    assert rc == 0

    captured = capfd.readouterr()
    assert "out" in captured.out
    assert "err" in captured.err

    with store.locked() as conn:
        rows = conn.execute("SELECT stream, message FROM logs ORDER BY message").fetchall()
    store.close()
    assert rows == [("stderr", "err"), ("stdout", "out")]


def test_propagates_nonzero_exit_code(make_config: ConfigFactory) -> None:
    store = LogStore()
    rc = Wrapper(make_config(), store).run(["sh", "-c", "exit 3"])
    store.close()
    assert rc == 3


def test_records_carry_service_and_level(make_config: ConfigFactory) -> None:
    store = LogStore()
    config = make_config(service="svc-a")
    Wrapper(config, store).run(["sh", "-c", "echo ERROR boom"])
    with store.locked() as conn:
        row = conn.execute("SELECT service, level, message FROM logs").fetchone()
    store.close()
    assert row == ("svc-a", "error", "ERROR boom")
