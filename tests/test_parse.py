from __future__ import annotations

import pytest

from daffy.parse import parse_line


@pytest.mark.parametrize(
    ("line", "want_level", "want_fields"),
    [
        ("just a plain message", "", None),
        ("ERROR something broke", "error", None),
        ("a WARNING about disk", "warn", None),
        ("DEBUG: starting up", "debug", None),
        ('{"level":"info","msg":"hi"}', "info", '{"level":"info","msg":"hi"}'),
        ('{"severity":"ERROR","msg":"boom"}', "error", '{"severity":"ERROR","msg":"boom"}'),
        ('{"msg":"no level here"}', "", '{"msg":"no level here"}'),
        ("{not valid json}", "", None),
        ("", "", None),
    ],
)
def test_parse_line(line: str, want_level: str, want_fields: str | None) -> None:
    level, fields = parse_line(line)
    assert level == want_level
    assert fields == want_fields
