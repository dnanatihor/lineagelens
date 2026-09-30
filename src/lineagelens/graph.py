"""Lineage graph assembled from a project of SQL statements."""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from lineagelens.models import Diagnostic, Edge, Statement


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
