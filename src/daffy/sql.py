"""SQL helpers shared by daffy and scrooge."""

from __future__ import annotations


def sql_literal(value: str) -> str:
    """Quote a string as a SQL literal (single quotes doubled).

    Used for the statements that can't be parameterized — ATTACH URIs, COPY paths, and
    other DuckDB DDL/CALLs where bind parameters aren't accepted.
    """
    return "'" + value.replace("'", "''") + "'"
