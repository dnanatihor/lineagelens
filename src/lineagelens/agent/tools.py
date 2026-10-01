"""Deterministic wrappers over lineage search, walks, and impact."""

from __future__ import annotations

from langchain_core.tools import BaseTool, tool

from lineagelens.graph import LineageGraph
from lineagelens.impact import format_impact
from lineagelens.impact import impact_of_change as change_impact
from lineagelens.impact import impact_of_drop as drop_impact
from lineagelens.models import Edge


def build_tools(graph: LineageGraph) -> list[BaseTool]:
    """Return the §8.2 tools bound to one graph."""

    def known(column: str) -> bool:
        return any(column in (edge.source.fqn(), edge.target.fqn()) for edge in graph.edges)

    def missing(column: str) -> str:
        return f"Column not found: {column}"

    def render_edges(edges: list[Edge]) -> str:
        if not edges:
            return "No edges."
        return "\n".join(
            f"{edge.file}:{edge.line} {edge.source.fqn()} -> {edge.target.fqn()} "
            f"{edge.type} {edge.subtype}"
            for edge in edges
        )

    @tool
    def search_columns(query: str) -> str:
        """Find columns whose fully qualified name contains the query."""
        needle = query.strip().lower()
        names = sorted(
            {
                column.fqn()
                for edge in graph.edges
                for column in (edge.source, edge.target)
                if needle and needle in column.fqn().lower()
            }
        )
        if not names:
            return f"No column found matching {query}."
        return "\n".join(names)

    @tool
    def upstream(column: str) -> str:
        """List columns that flow into this column, with file:line evidence."""
        if not known(column):
            return missing(column)
        columns = graph.upstream(column)
        names = {column, *(item.fqn() for item in columns)}
        edges = [
            edge
            for edge in graph.edges
            if edge.source.fqn() in names and edge.target.fqn() in names
        ]
        lines = [item.fqn() for item in columns] or ["No upstream columns."]
        return "\n".join(lines) + "\n" + render_edges(edges)

    @tool
    def downstream(column: str) -> str:
        """List columns this column flows into, with file:line evidence."""
        if not known(column):
            return missing(column)
        columns = graph.downstream(column)
        names = {column, *(item.fqn() for item in columns)}
        edges = [
            edge
            for edge in graph.edges
            if edge.source.fqn() in names and edge.target.fqn() in names
        ]
        lines = [item.fqn() for item in columns] or ["No downstream columns."]
        return "\n".join(lines) + "\n" + render_edges(edges)

    @tool
    def impact_of_change(column: str) -> str:
        """Columns whose values change, and columns whose results may change."""
        if not known(column):
            return missing(column)
        return format_impact(change_impact(graph, column))

    @tool
    def impact_of_drop(column: str) -> str:
        """Statements that will break, and tables downstream of those statements."""
        if not known(column):
            return missing(column)
        return format_impact(drop_impact(graph, column))

    @tool
    def explain_path(source: str, destination: str) -> str:
        """Edges on a path from source column to destination column."""
        if not known(source):
            return missing(source)
        if not known(destination):
            return missing(destination)
        edges = graph.explain_path(source, destination)
        if not edges:
            return f"No path from {source} to {destination}."
        return render_edges(edges)

    tools: list[BaseTool] = [
        search_columns,
        upstream,
        downstream,
        impact_of_change,
        impact_of_drop,
        explain_path,
    ]
    return tools
