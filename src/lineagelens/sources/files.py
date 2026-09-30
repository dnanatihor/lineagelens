"""Load SQL files and split them into statements."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import sqlglot
from sqlglot import TokenType
from sqlglot.errors import SqlglotError


def discover_sql_files(paths: Sequence[Path]) -> list[Path]:
    """Return SQL files from files or directories, in stable path order."""
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(sorted(item for item in path.rglob("*.sql") if item.is_file()))
        elif path.is_file() and path.suffix == ".sql":
            found.append(path)
    return found


def statement_chunks(sql: str, dialect: str) -> list[tuple[str, int]]:
    """Split SQL into statements and each statement's starting line."""
    try:
        tokens = sqlglot.tokenize(sql, read=dialect)
    except SqlglotError:
        return [(sql, 1)] if sql.strip() else []
    chunks: list[tuple[str, int]] = []
    start: int | None = None
    start_line = 1
    for token in tokens:
        if token.token_type == TokenType.SEMICOLON:
            if start is not None:
                chunks.append((sql[start : token.end], start_line))
                start = None
            continue
        if start is None:
            start = token.start
            start_line = token.line
    if start is not None:
        chunks.append((sql[start:], start_line))
    return chunks
