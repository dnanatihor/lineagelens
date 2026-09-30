"""Lineage graph assembled from a project of SQL statements."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import networkx as nx

from lineagelens.models import ColumnRef, Diagnostic, Edge, Statement


@dataclass(frozen=True)
class LineageGraph:
    """Column graph plus the statements and diagnostics that produced it."""

    statements: tuple[Statement, ...]
    edges: tuple[Edge, ...]
    diagnostics: tuple[Diagnostic, ...]

    def __post_init__(self) -> None:
        graph: nx.MultiDiGraph = nx.MultiDiGraph()
        for edge in self.edges:
            graph.add_node(edge.source.fqn(), table=edge.source.table)
            graph.add_node(edge.target.fqn(), table=edge.target.table)
            graph.add_edge(
                edge.source.fqn(),
                edge.target.fqn(),
                key=f"{edge.type}:{edge.subtype}:{edge.statement_id}:{edge.expression}",
                edge=edge,
            )
        object.__setattr__(self, "_graph", graph)

    @property
    def graph(self) -> nx.MultiDiGraph:
        stored = getattr(self, "_graph", None)
        if not isinstance(stored, nx.MultiDiGraph):
            message = "lineage graph was not initialised"
            raise RuntimeError(message)
        return stored

    def upstream(
        self,
        column: str,
        *,
        types: tuple[str, ...] = ("DIRECT", "INDIRECT"),
        depth: int | None = None,
    ) -> list[ColumnRef]:
        return _walk(self, column, types=types, depth=depth, downstream=False)

    def downstream(
        self,
        column: str,
        *,
        types: tuple[str, ...] = ("DIRECT", "INDIRECT"),
        depth: int | None = None,
    ) -> list[ColumnRef]:
        return _walk(self, column, types=types, depth=depth, downstream=True)

    def explain_path(self, source: str, destination: str) -> list[Edge]:
        """Shortest path from source column to destination, edges in order."""
        adjacency: dict[str, list[Edge]] = {}
        for edge in self.edges:
            adjacency.setdefault(edge.source.fqn(), []).append(edge)
        queue: deque[tuple[str, tuple[Edge, ...]]] = deque([(source, ())])
        seen = {source}
        while queue:
            node, path = queue.popleft()
            if node == destination and path:
                return list(path)
            for edge in adjacency.get(node, []):
                target = edge.target.fqn()
                if target in seen:
                    continue
                seen.add(target)
                queue.append((target, (*path, edge)))
        return []


def _walk(
    graph: LineageGraph,
    column: str,
    *,
    types: tuple[str, ...],
    depth: int | None,
    downstream: bool,
) -> list[ColumnRef]:
    adjacency: dict[str, list[Edge]] = {}
    for edge in graph.edges:
        if edge.type not in types:
            continue
        key = edge.source.fqn() if downstream else edge.target.fqn()
        adjacency.setdefault(key, []).append(edge)
    found: dict[str, ColumnRef] = {}
    queue: deque[tuple[str, int]] = deque([(column, 0)])
    seen = {column}
    while queue:
        node, distance = queue.popleft()
        if depth is not None and distance >= depth:
            continue
        for edge in adjacency.get(node, []):
            nxt = edge.target if downstream else edge.source
            if nxt.fqn() in seen:
                continue
            seen.add(nxt.fqn())
            found[nxt.fqn()] = nxt
            queue.append((nxt.fqn(), distance + 1))
    return [found[name] for name in sorted(found)]
