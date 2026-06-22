"""Wrap a child process, teeing its stdout/stderr to the console and the local buffer.

Console output happens first on every line so that logging never blocks on DuckDB and
tools like ``kubectl logs`` see output unchanged. Parsed records are handed to a single
writer thread that batches inserts into the :class:`~daffy.store.LogStore`.
"""

from __future__ import annotations

import queue
import signal
import subprocess
import sys
import threading
from collections.abc import Callable
from datetime import datetime
from typing import IO, Any, BinaryIO

from daffy.config import Config
from daffy.parse import parse_line
from daffy.schema import LogRecord
from daffy.store import LogStore

_BATCH_MAX = 256
_SENTINEL = object()


class Wrapper:
    def __init__(
        self,
        config: Config,
        store: LogStore,
        on_records_written: Callable[[], None] | None = None,
    ) -> None:
        self._config = config
        self._store = store
        self._on_written = on_records_written
        self._queue: queue.Queue[object] = queue.Queue()

    def run(self, command: list[str]) -> int:
        proc = subprocess.Popen(  # noqa: S603 - command is supplied intentionally by the caller
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert proc.stdout is not None
        assert proc.stderr is not None

        writer = threading.Thread(target=self._writer_loop, name="daffy-writer")
        writer.start()
        readers = [
            self._start_reader(proc.stdout, "stdout", sys.stdout.buffer),
            self._start_reader(proc.stderr, "stderr", sys.stderr.buffer),
        ]

        with self._forward_signals(proc):
            returncode = proc.wait()

        for reader in readers:
            reader.join()
        self._queue.put(_SENTINEL)
        writer.join()
        return returncode

    def _start_reader(self, pipe: IO[bytes], stream: str, console: BinaryIO) -> threading.Thread:
        thread = threading.Thread(
            target=self._read_stream,
            args=(pipe, stream, console),
            name=f"daffy-reader-{stream}",
        )
        thread.start()
        return thread

    def _read_stream(self, pipe: IO[bytes], stream: str, console: BinaryIO) -> None:
        for raw in iter(pipe.readline, b""):
            console.write(raw)
            console.flush()
            message = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            level, fields = parse_line(message)
            self._queue.put(
                LogRecord(
                    capture_time=datetime.now(),
                    service=self._config.service,
                    stream=stream,
                    message=message,
                    level=level,
                    pod=self._config.pod,
                    node=self._config.node,
                    fields=fields,
                )
            )

    def _writer_loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                return
            batch: list[LogRecord] = [item]  # type: ignore[list-item]
            while len(batch) < _BATCH_MAX:
                try:
                    nxt = self._queue.get_nowait()
                except queue.Empty:
                    break
                if nxt is _SENTINEL:
                    self._store.insert_many(batch)
                    self._notify()
                    return
                batch.append(nxt)  # type: ignore[arg-type]
            self._store.insert_many(batch)
            self._notify()

    def _notify(self) -> None:
        if self._on_written is not None:
            self._on_written()

    @staticmethod
    def _forward_signals(proc: subprocess.Popen[bytes]) -> _SignalForwarder:
        return _SignalForwarder(proc)


class _SignalForwarder:
    """Forward SIGTERM/SIGINT to the child for the duration of the context."""

    _SIGNALS = (signal.SIGTERM, signal.SIGINT)

    def __init__(self, proc: subprocess.Popen[bytes]) -> None:
        self._proc = proc
        self._previous: dict[int, Any] = {}

    def __enter__(self) -> _SignalForwarder:
        for sig in self._SIGNALS:
            self._previous[sig] = signal.getsignal(sig)
            signal.signal(sig, self._handle)
        return self

    def __exit__(self, *_exc: object) -> None:
        for sig, handler in self._previous.items():
            signal.signal(sig, handler)

    def _handle(self, signum: int, _frame: object) -> None:
        if self._proc.poll() is None:
            self._proc.send_signal(signum)
