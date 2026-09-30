"""Export a Mermaid flowchart of table or column lineage."""

from __future__ import annotations

from lineagelens.graph import LineageGraph


def export_mermaid(graph: LineageGraph, *, level: str = "table") -> str:
    if level == "column":
        lines = ["flowchart LR"]
        seen: set[tuple[str, str]] = set()
        for edge in graph.edges:
            pair = (edge.source.fqn(), edge.target.fqn())
            if pair in seen:
                continue
            seen.add(pair)
            lines.append(f"  {_node(edge.source.fqn())} --> {_node(edge.target.fqn())}")
        return "\n".join(lines) + "\n"
    links: set[tuple[str, str]] = set()
    for statement in graph.statements:
        if statement.target_table is None:
            continue
        for read in statement.reads:
            links.add((read, statement.target_table))
    lines = ["flowchart LR"]
    for source, target in sorted(links):
        lines.append(f"  {_node(source)} --> {_node(target)}")
    return "\n".join(lines) + "\n"


def _node(name: str) -> str:
    return name.replace(".", "_").replace('"', "")
