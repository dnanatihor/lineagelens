"""Declared schema registry used to qualify statements (SPEC.md §5.2, §5.4)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from lineagelens.models import normalise_identifier

TableColumns = dict[str, str]


def _table_key(table_fqn: str) -> str:
    return ".".join(normalise_identifier(part) for part in table_fqn.split(".") if part)


class SchemaRegistry:
    """Column types declared in ``schema.yaml`` or passed in as a mapping.

    Downstream statement accumulation is added in Phase 2. ``as_mapping`` is
    the shape ``sqlglot.optimizer.qualify.qualify`` accepts.
    """

    def __init__(self, tables: Mapping[str, Mapping[str, str]] | None = None) -> None:
        self._tables: dict[str, TableColumns] = {}
        for table_fqn, columns in (tables or {}).items():
            self._tables[_table_key(table_fqn)] = {
                normalise_identifier(name): str(column_type)
                for name, column_type in columns.items()
            }

    @classmethod
    def from_yaml(cls, path: Path) -> SchemaRegistry:
        loaded: object = yaml.safe_load(path.read_text())
        if loaded is None:
            return cls()
        if not isinstance(loaded, dict):
            message = "schema.yaml must be a mapping of table FQN to columns"
            raise ValueError(message)
        tables: dict[str, dict[str, str]] = {}
        for table_fqn, columns in loaded.items():
            if not isinstance(table_fqn, str) or not isinstance(columns, dict):
                message = "schema.yaml must be a mapping of table FQN to columns"
                raise ValueError(message)
            tables[table_fqn] = {
                str(name): str(column_type) for name, column_type in columns.items()
            }
        return cls(tables)

    def column_names(self, table_fqn: str) -> tuple[str, ...] | None:
        columns = self._tables.get(_table_key(table_fqn))
        if columns is None:
            return None
        return tuple(columns)

    def as_mapping(self) -> dict[str, Any]:
        """Nest ``schema.table`` keys into the mapping sqlglot expects."""
        root: dict[str, Any] = {}
        for table_fqn, columns in self._tables.items():
            if not columns:
                continue
            parts = table_fqn.split(".")
            cursor = root
            for part in parts[:-1]:
                child = cursor.get(part)
                if not isinstance(child, dict):
                    child = {}
                    cursor[part] = child
                cursor = child
            cursor[parts[-1]] = dict(columns)
        return root
