"""FastAPI app that serves the viewer and the graph API."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from lineagelens.graph import LineageGraph
from lineagelens.impact import impact_of_change, impact_of_drop
from lineagelens.models import ColumnRef, Edge

COLUMN_VIEW_LIMIT = 300


def viewer_dist() -> Path:
    return Path(__file__).resolve().parent / "web" / "dist"


def table_name(column: ColumnRef) -> str:
    return ".".join(part for part in (column.database, column.schema_, column.table) if part)


def graph_payload(graph: LineageGraph) -> dict[str, object]:
    columns: dict[str, set[str]] = {}
    for edge in graph.edges:
        columns.setdefault(table_name(edge.source), set()).add(edge.source.column)
        columns.setdefault(table_name(edge.target), set()).add(edge.target.column)
    view = "column" if len(columns) <= COLUMN_VIEW_LIMIT else "table"
    tables = [{"name": name, "columns": sorted(cols)} for name, cols in sorted(columns.items())]
    return {
        "view": view,
        "tables": tables,
        "edges": [_edge_payload(edge) for edge in graph.edges],
    }


def _edge_payload(edge: Edge) -> dict[str, object]:
    return {
        "source_table": table_name(edge.source),
        "source_column": edge.source.column,
        "target_table": table_name(edge.target),
        "target_column": edge.target.column,
        "source": edge.source.fqn(),
        "target": edge.target.fqn(),
        "type": edge.type,
        "subtype": edge.subtype,
        "expression": edge.expression,
        "file": edge.file,
        "line": edge.line,
        "statement_id": edge.statement_id,
    }


def search_columns(graph: LineageGraph, query: str) -> list[dict[str, str]]:
    needle = query.strip().lower()
    found: dict[str, dict[str, str]] = {}
    for edge in graph.edges:
        for column in (edge.source, edge.target):
            fqn = column.fqn()
            if needle and needle not in fqn.lower():
                continue
            found[fqn] = {
                "fqn": fqn,
                "table": table_name(column),
                "column": column.column,
            }
    return [found[key] for key in sorted(found)]


def create_app(graph: LineageGraph, *, dist: Path | None = None) -> FastAPI:
    app = FastAPI(title="LineageLens")
    static = dist if dist is not None else viewer_dist()

    @app.get("/api/graph")
    def api_graph() -> dict[str, object]:
        return graph_payload(graph)

    @app.get("/api/impact")
    def api_impact(
        change: str | None = Query(default=None),
        drop: str | None = Query(default=None),
    ) -> dict[str, object]:
        if (change is None and drop is None) or (change is not None and drop is not None):
            raise HTTPException(status_code=400, detail="Provide exactly one of change or drop.")
        if change is not None:
            changed = impact_of_change(graph, change)
            return {
                "kind": "change",
                "column": change,
                "direct": [column.fqn() for column in changed.direct],
                "indirect": [column.fqn() for column in changed.indirect],
                "evidence": [_edge_payload(edge) for edge in changed.evidence],
            }
        if drop is None:
            raise HTTPException(status_code=400, detail="Provide exactly one of change or drop.")
        dropped = impact_of_drop(graph, drop)
        return {
            "kind": "drop",
            "column": drop,
            "failing_statements": list(dropped.failing_statements),
            "broken_tables": list(dropped.broken_tables),
            "affected_columns": [column.fqn() for column in dropped.affected_columns],
            "evidence": [_edge_payload(edge) for edge in dropped.evidence],
        }

    @app.get("/api/search")
    def api_search(q: str = "") -> dict[str, object]:
        return {"results": search_columns(graph, q)}

    if static.is_dir() and (static / "index.html").is_file():
        assets = static / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(static / "index.html")

        @app.get("/{path:path}")
        def spa(path: str) -> FileResponse:
            candidate = (static / path).resolve()
            if candidate.is_file() and static.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(static / "index.html")

    return app
