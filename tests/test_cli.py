from __future__ import annotations

import pytest

from daffy.cli import _split_command, main


@pytest.mark.parametrize(
    ("argv", "want_opts", "want_cmd"),
    [
        (["--service", "x", "--", "ls", "-l"], ["--service", "x"], ["ls", "-l"]),
        (["ls", "-l"], ["ls", "-l"], []),
        (["--service", "x", "--"], ["--service", "x"], []),
    ],
)
def test_split_command(argv: list[str], want_opts: list[str], want_cmd: list[str]) -> None:
    assert _split_command(argv) == (want_opts, want_cmd)


def test_main_propagates_exit_code() -> None:
    assert main(["--service", "demo", "--", "sh", "-c", "exit 5"]) == 5


def test_main_requires_command() -> None:
    assert main(["--service", "demo"]) == 2


def test_main_reports_missing_command(capfd: pytest.CaptureFixture[str]) -> None:
    rc = main(["--service", "demo", "--", "this-command-does-not-exist-xyz"])
    assert rc == 127
    assert "command not found" in capfd.readouterr().err


def test_main_requires_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SERVICE_NAME", raising=False)
    assert main(["--", "true"]) == 2
