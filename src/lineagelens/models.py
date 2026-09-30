"""Core lineage models (SPEC.md §4 and §6)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EdgeType = Literal["DIRECT", "INDIRECT"]
EdgeSubtype = Literal[
    "IDENTITY",
    "TRANSFORMATION",
    "AGGREGATION",
    "FILTER",
    "JOIN",
    "GROUP_BY",
    "SORT",
    "WINDOW",
    "CONDITIONAL",
]
StatementKind = Literal["ctas", "insert_select", "create_view", "select", "unsupported"]
DiagnosticCode = Literal["L001", "L002", "L003", "L004", "L005", "L006"]
Severity = Literal["error", "warning", "info"]

_FROZEN = ConfigDict(frozen=True, populate_by_name=True)


def normalise_identifier(identifier: str) -> str:
    """Lowercase unquoted identifiers and preserve quoted ones (SPEC.md §12)."""
    if _is_quoted(identifier):
        return identifier
    return identifier.lower()


def _is_quoted(identifier: str) -> bool:
    if len(identifier) < 2:
        return False
    if identifier[0] == identifier[-1] and identifier[0] in {'"', "`"}:
        return True
    return identifier[0] == "[" and identifier[-1] == "]"


class ColumnRef(BaseModel):
    """A column addressed by optional database, schema, table, and column name."""

    model_config = _FROZEN

    database: str | None = None
    schema_: str | None = Field(default=None, alias="schema")
    table: str
    column: str

    def fqn(self) -> str:
        """Return the dotted name, normalised per dialect case rules."""
        parts = [
            normalise_identifier(part)
            for part in (self.database, self.schema_, self.table, self.column)
            if part is not None
        ]
        return ".".join(parts)


class Edge(BaseModel):
    """One column-level lineage edge."""

    model_config = _FROZEN

    source: ColumnRef
    target: ColumnRef
    type: EdgeType
    subtype: EdgeSubtype
    expression: str = Field(max_length=200)
    statement_id: str
    file: str
    line: int = Field(ge=1)


class Statement(BaseModel):
    """One SQL statement that may read tables and write a target."""

    model_config = _FROZEN

    id: str
    file: str
    index: int = Field(ge=0)
    line: int = Field(ge=1)
    kind: StatementKind
    target_table: str | None
    reads: tuple[str, ...]


class Diagnostic(BaseModel):
    """A recorded extraction problem. Codes are L001 through L006."""

    model_config = _FROZEN

    code: DiagnosticCode
    severity: Severity
    statement_id: str | None
    message: str


class ChangeImpact(BaseModel):
    """Downstream effect of a column's values changing (SPEC.md §6)."""

    model_config = _FROZEN

    direct: tuple[ColumnRef, ...]
    indirect: tuple[ColumnRef, ...]
    evidence: tuple[Edge, ...] = ()


class DropImpact(BaseModel):
    """Downstream effect of a column no longer existing (SPEC.md §6)."""

    model_config = _FROZEN

    failing_statements: tuple[str, ...]
    broken_tables: tuple[str, ...]
    affected_columns: tuple[ColumnRef, ...]
    evidence: tuple[Edge, ...] = ()


ImpactResult = ChangeImpact | DropImpact
