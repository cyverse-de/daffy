"""Tail Scrooge's Quack server log and surface upload activity as Python logs.

Remote daffy uploads are handled inside the embedded Quack server, so they don't pass
through Scrooge's Python code. Instead we enable Quack's own logging (see
:meth:`ScroogeServer.drain_quack_log`) and a background thread polls it, logging when a
daffy connects and when each upload (an ``APPEND_REQUEST``) completes. Quack log entries
are emitted on completion, so ``duration_ms`` tells how long the upload took.
"""

from __future__ import annotations

import logging
import threading

import duckdb

from scrooge.server import ScroogeServer

log = logging.getLogger("scrooge.monitor")


class QuackLogMonitor:
    def __init__(self, server: ScroogeServer, interval: float) -> None:
        self._server = server
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="scrooge-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval + 5.0)
        self._drain()

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            self._drain()

    def _drain(self) -> None:
        try:
            rows = self._server.drain_quack_log()
        except duckdb.Error as err:
            log.warning("could not read quack log: %s", err)
            return
        for message_type, _response_type, duration_ms, connection_id, error in rows:
            if error:
                log.warning("upload error on quack connection %s: %s", connection_id, error)
            elif message_type == "CONNECTION_REQUEST":
                # The connection request itself carries no connection id yet.
                log.info("daffy connected")
            elif message_type == "APPEND_REQUEST":
                log.info(
                    "upload received on quack connection %s (%d ms)", connection_id, duration_ms
                )
