from __future__ import annotations

from collections.abc import Callable

import pytest

from daffy.config import Config, build_config

ConfigFactory = Callable[..., Config]


@pytest.fixture
def make_config() -> ConfigFactory:
    def _make(service: str = "demo", local_db: str = ":memory:", **overrides: object) -> Config:
        kwargs: dict[str, object] = {
            "service": service,
            "local_db": local_db,
            "pod": None,
            "node": None,
            "scrooge_uri": None,
            "scrooge_token": None,
            "flush_bytes": None,
            "flush_interval": None,
            "max_buffer_bytes": None,
        }
        kwargs.update(overrides)
        return build_config(**kwargs)  # type: ignore[arg-type]

    return _make
