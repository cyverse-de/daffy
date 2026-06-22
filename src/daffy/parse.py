"""Best-effort parsing of raw log lines into a level and structured fields.

Parsing must never raise into the logging path: an unparseable line is still a valid
log record with an empty level and no fields.
"""

from __future__ import annotations

import json
import re

# Common level tokens emitted by typical loggers, checked case-insensitively.
_LEVELS = ("trace", "debug", "info", "warn", "warning", "error", "fatal", "panic")
_LEVEL_RE = re.compile(
    r"\b(" + "|".join(_LEVELS) + r")\b",
    re.IGNORECASE,
)


def parse_line(message: str) -> tuple[str, str | None]:
    """Return ``(level, fields_json)`` for a raw log line.

    ``fields_json`` is the compact JSON text of the line's fields when the line is a JSON
    object, otherwise ``None``. ``level`` is the detected level (lower-cased) or ``""``.
    """
    fields_json: str | None = None
    level = ""

    stripped = message.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            obj = json.loads(stripped)
        except (ValueError, TypeError):
            obj = None
        if isinstance(obj, dict):
            fields_json = json.dumps(obj, separators=(",", ":"))
            level = _level_from_fields(obj)

    if not level:
        match = _LEVEL_RE.search(message)
        if match:
            level = match.group(1).lower()

    if level == "warning":
        level = "warn"
    return level, fields_json


def _level_from_fields(obj: dict[str, object]) -> str:
    for key in ("level", "lvl", "severity"):
        value = obj.get(key)
        if isinstance(value, str) and value:
            return value.lower()
    return ""
