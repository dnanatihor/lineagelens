"""Change and drop impact over a lineage graph (SPEC.md section 6)."""

from __future__ import annotations

from collections import deque

from lineagelens.graph import LineageGraph
from lineagelens.models import ChangeImpact, ColumnRef, DropImpact, Edge, ImpactResult


def impact_of_change(graph: LineageGraph, column: str) -> ChangeImpact:
    """Columns whose values change, and columns whose rows or grouping may change."""
    start = column
    direct_nodes, direct_edges = _reachable(graph, start, indirect=False)
    indirect_nodes, indirect_edges = _reachable(graph, start, indirect=True)
    indirect_nodes -= direct_nodes
    return ChangeImpact(
        direct=_columns(graph, direct_nodes),
        indirect=_columns(graph, indirect_nodes),
        evidence=_sorted_edges([*direct_edges, *indirect_edges]),
    )


def impact_of_drop(graph: LineageGraph, column: str) -> DropImpact:
    """Statements that reference the column, and tables downstream of their targets."""
    references = [edge for edge in graph.edges if edge.source.fqn() == column]
    failing = tuple(sorted({edge.statement_id for edge in references}))
    statements = {statement.id: statement for statement in graph.statements}
    seeds: list[str] = []
    for statement_id in failing:
        statement = statements.get(statement_id)
        if statement is not None and statement.target_table and statement.target_table not in seeds:
            seeds.append(statement.target_table)
    broken = _downstream_tables(graph, seeds)
    affected = _columns_of_tables(graph, set(broken))
    return DropImpact(
        failing_statements=failing,
        broken_tables=tuple(broken),
        affected_columns=affected,
        evidence=_sorted_edges(references),
    )


def format_impact(result: ImpactResult) -> str:
    """Text report that cites each evidence edge as file:line."""
    lines: list[str] = []
    if isinstance(result, ChangeImpact):
        lines.append("direct:")
        lines.extend(f"  {column.fqn()}" for column in result.direct)
        lines.append("indirect:")
        lines.extend(f"  {column.fqn()}" for column in result.indirect)
    else:
        lines.append("failing statements:")
        lines.extend(f"  {statement_id}" for statement_id in result.failing_statements)
        lines.append("broken tables:")
        lines.extend(f"  {table}" for table in result.broken_tables)
    lines.append("evidence:")
    lines.extend(
        f"  {edge.file}:{edge.line} {edge.source.fqn()} -> {edge.target.fqn()}"
        for edge in result.evidence
    )
    return "\n".join(lines)


def _reachable(graph: LineageGraph, start: str, *, indirect: bool) -> tuple[set[str], list[Edge]]:
    adjacency: dict[str, list[Edge]] = {}
    for edge in graph.edges:
        adjacency.setdefault(edge.source.fqn(), []).append(edge)
    found: set[str] = set()
    evidence: list[Edge] = []
    seen: set[tuple[str, bool]] = set()
    queue: deque[tuple[str, bool, tuple[Edge, ...]]] = deque([(start, False, ())])
    while queue:
        node, saw_indirect, path = queue.popleft()
        state = (node, saw_indirect)
        if state in seen:
            continue
        seen.add(state)
        if node != start and saw_indirect == indirect:
            found.add(node)
            evidence.extend(path)
        for edge in adjacency.get(node, []):
            if indirect:
                next_saw = saw_indirect or edge.type == "INDIRECT"
            elif edge.type != "DIRECT":
                continue
            else:
                next_saw = False
            queue.append((edge.target.fqn(), next_saw, (*path, edge)))
    return found, evidence


def _downstream_tables(graph: LineageGraph, seeds: list[str]) -> list[str]:
    readers: dict[str, list[str]] = {}
    for statement in graph.statements:
        if statement.target_table is None:
            continue
        for read in statement.reads:
            readers.setdefault(read, [])
            if statement.target_table not in readers[read]:
                readers[read].append(statement.target_table)
    broken = list(seeds)
    seen = set(seeds)
    queue = deque(seeds)
    while queue:
        table = queue.popleft()
        for downstream in readers.get(table, []):
            if downstream not in seen:
                seen.add(downstream)
                broken.append(downstream)
                queue.append(downstream)
    return broken


def _columns(graph: LineageGraph, names: set[str]) -> tuple[ColumnRef, ...]:
    return tuple(_lookup(graph, name) for name in sorted(names))


def _columns_of_tables(graph: LineageGraph, tables: set[str]) -> tuple[ColumnRef, ...]:
    found: dict[str, ColumnRef] = {}
    for edge in graph.edges:
        for column in (edge.source, edge.target):
            if _table_fqn(column) in tables:
                found.setdefault(column.fqn(), column)
    return tuple(found[name] for name in sorted(found))


def _lookup(graph: LineageGraph, fqn: str) -> ColumnRef:
    for edge in graph.edges:
        if edge.source.fqn() == fqn:
            return edge.source
        if edge.target.fqn() == fqn:
            return edge.target
    return _parse_column(fqn)


def _parse_column(fqn: str) -> ColumnRef:
    parts = fqn.split(".")
    if len(parts) == 3:
        payload: dict[str, str | None] = {"schema": parts[0], "table": parts[1], "column": parts[2]}
    elif len(parts) == 4:
        payload = {
            "database": parts[0],
            "schema": parts[1],
            "table": parts[2],
            "column": parts[3],
        }
    else:
        payload = {"table": parts[-2], "column": parts[-1]}
    return ColumnRef.model_validate(payload)


def _table_fqn(column: ColumnRef) -> str:
    parts = [part for part in (column.database, column.schema_, column.table) if part is not None]
    return ".".join(parts)


def _sorted_edges(edges: list[Edge]) -> tuple[Edge, ...]:
    unique: dict[tuple[str, str, str, str, str], Edge] = {}
    for edge in edges:
        key = (
            edge.source.fqn(),
            edge.target.fqn(),
            edge.type,
            edge.subtype,
            edge.statement_id,
        )
        unique.setdefault(key, edge)
    return tuple(unique[key] for key in sorted(unique))
