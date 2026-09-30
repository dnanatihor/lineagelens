"""Order a SQL project and assemble its column lineage graph."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from lineagelens.extract import StatementExtraction, extract_sql
from lineagelens.graph import LineageGraph
from lineagelens.models import Diagnostic, Edge, Statement
from lineagelens.schema import SchemaRegistry
from lineagelens.sources.files import discover_sql_files


@dataclass(frozen=True)
class _Planned:
    sql: str
    statement: Statement
    sort_key: tuple[str, int]


def build_project(
    paths: Sequence[Path],
    *,
    dialect: str = "postgres",
    schema: SchemaRegistry | Path | Mapping[str, Mapping[str, str]] | None = None,
    indirect: bool = True,
) -> LineageGraph:
    """Build direct and indirect lineage for SQL files, in dependency order."""
    registry = _registry(schema)
    planned = _plan(paths, dialect)
    order, cycle_ids = _execution_order(planned)
    statements: list[Statement] = []
    edges: list[Edge] = []
    diagnostics: list[Diagnostic] = []
    for index in order:
        item = planned[index]
        extracted = extract_sql(
            item.sql,
            file=item.statement.file,
            dialect=dialect,
            schema=registry,
            indirect=indirect,
            index_offset=item.statement.index,
        )
        if not extracted:
            continue
        result = extracted[0]
        statements.append(result.statement)
        edges.extend(result.edges)
        diagnostics.extend(result.diagnostics)
        if result.statement.id in cycle_ids:
            diagnostics.append(
                Diagnostic(
                    code="L006",
                    severity="error",
                    statement_id=result.statement.id,
                    message="Cyclic table dependency.",
                )
            )
        _register_outputs(registry, result)
    return LineageGraph(
        statements=tuple(statements),
        edges=tuple(
            sorted(
                edges,
                key=lambda edge: (
                    edge.source.fqn(),
                    edge.target.fqn(),
                    edge.type,
                    edge.subtype,
                    edge.statement_id,
                ),
            )
        ),
        diagnostics=tuple(diagnostics),
    )


def _registry(
    schema: SchemaRegistry | Path | Mapping[str, Mapping[str, str]] | None,
) -> SchemaRegistry:
    if isinstance(schema, SchemaRegistry):
        return schema
    if isinstance(schema, Path):
        return SchemaRegistry.from_yaml(schema)
    return SchemaRegistry(schema)


def _plan(paths: Sequence[Path], dialect: str) -> list[_Planned]:
    planned: list[_Planned] = []
    for path in discover_sql_files(paths):
        text = path.read_text()
        previews = extract_sql(text, file=path.name, dialect=dialect, indirect=False)
        chunks = _chunks_matching(text, dialect, len(previews))
        for preview, sql in zip(previews, chunks, strict=False):
            planned.append(
                _Planned(
                    sql=sql,
                    statement=preview.statement,
                    sort_key=(path.name, preview.statement.index),
                )
            )
    return planned


def _chunks_matching(text: str, dialect: str, count: int) -> list[str]:
    from lineagelens.sources.files import statement_chunks

    chunks = [sql for sql, _line in statement_chunks(text, dialect)]
    if len(chunks) == count:
        return chunks
    return [text] * count if count else []


def _execution_order(planned: list[_Planned]) -> tuple[list[int], set[str]]:
    writers: dict[str, list[int]] = {}
    for index, item in enumerate(planned):
        target = item.statement.target_table
        if target is not None:
            writers.setdefault(target, []).append(index)
    depends_on: dict[int, set[int]] = {}
    for index, item in enumerate(planned):
        upstream: set[int] = set()
        for read in item.statement.reads:
            for writer in writers.get(read, []):
                if writer != index:
                    upstream.add(writer)
        depends_on[index] = upstream

    remaining = set(range(len(planned)))
    order: list[int] = []
    while remaining:
        ready = sorted(
            (index for index in remaining if not (depends_on[index] & remaining)),
            key=lambda index: planned[index].sort_key,
        )
        if not ready:
            break
        nxt = ready[0]
        remaining.remove(nxt)
        order.append(nxt)

    cycle_ids: set[str] = set()
    if remaining:
        blocked = sorted(remaining, key=lambda index: planned[index].sort_key)
        for index in blocked:
            if _in_cycle(index, remaining, depends_on):
                cycle_ids.add(planned[index].statement.id)
            order.append(index)
    return order, cycle_ids


def _in_cycle(start: int, remaining: set[int], depends_on: dict[int, set[int]]) -> bool:
    seen: set[int] = set()
    stack = list(depends_on[start] & remaining)
    while stack:
        current = stack.pop()
        if current == start:
            return True
        if current in seen:
            continue
        seen.add(current)
        stack.extend(depends_on[current] & remaining)
    return False


def _register_outputs(registry: SchemaRegistry, result: StatementExtraction) -> None:
    target = result.statement.target_table
    if target is None or not result.output_columns:
        return
    registry.register(target, [(column, "UNKNOWN") for column in result.output_columns])
