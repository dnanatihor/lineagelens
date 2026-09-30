"""Export the project graph as LineageLens JSON."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict

from lineagelens import __version__
from lineagelens.graph import LineageGraph
from lineagelens.models import Diagnostic, Edge, Statement


class GraphDocument(BaseModel):
    """Own export schema: statements, edges, diagnostics, and version."""

    model_config = ConfigDict(populate_by_name=True)

    version: str
    statements: tuple[Statement, ...]
    edges: tuple[Edge, ...]
    diagnostics: tuple[Diagnostic, ...]


def export_json(graph: LineageGraph) -> str:
    document = GraphDocument(
        version=__version__,
        statements=graph.statements,
        edges=graph.edges,
        diagnostics=graph.diagnostics,
    )
    return json.dumps(document.model_dump(mode="json", by_alias=True), indent=2) + "\n"


def load_json(text: str) -> LineageGraph:
    document = GraphDocument.model_validate(json.loads(text))
    return LineageGraph(
        statements=document.statements,
        edges=document.edges,
        diagnostics=document.diagnostics,
    )
