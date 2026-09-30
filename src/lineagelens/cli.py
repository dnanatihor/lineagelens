"""Command-line interface for build, impact, and export."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from lineagelens import __version__
from lineagelens.export.json import export_json, load_json
from lineagelens.export.mermaid import export_mermaid
from lineagelens.export.openlineage import export_openlineage
from lineagelens.graph import LineageGraph
from lineagelens.impact import format_impact, impact_of_change, impact_of_drop
from lineagelens.models import ImpactResult
from lineagelens.project import build_project
from lineagelens.sources.dbt import DbtProjectError, build_dbt

app = typer.Typer(
    no_args_is_help=True,
    help=f"LineageLens {__version__}: column-level SQL lineage.",
)


def _merge(left: LineageGraph, right: LineageGraph) -> LineageGraph:
    return LineageGraph(
        statements=(*left.statements, *right.statements),
        edges=(*left.edges, *right.edges),
        diagnostics=(*left.diagnostics, *right.diagnostics),
    )


def _unavailable(command: str) -> None:
    typer.echo(f"lineagelens {command} is not implemented yet.", err=True)
    raise typer.Exit(code=2)


def _require_graph(path: Path) -> None:
    if not path.is_file():
        typer.echo(f"Graph file does not exist: {path}", err=True)
        raise typer.Exit(code=2)


@app.command()
def build(
    paths: Annotated[list[Path] | None, typer.Argument(help="SQL files or directories.")] = None,
    dialect: Annotated[str, typer.Option("--dialect", help="SQL dialect.")] = "postgres",
    schema: Annotated[Path | None, typer.Option("--schema", help="Path to schema.yaml.")] = None,
    dbt: Annotated[Path | None, typer.Option("--dbt", help="dbt project directory.")] = None,
    no_indirect: Annotated[bool, typer.Option("--no-indirect")] = False,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Build a lineage graph from SQL files or a dbt project."""
    if dbt is not None and not (dbt / "target" / "manifest.json").is_file():
        typer.echo("dbt compile is required; target/manifest.json was not found.", err=True)
        raise typer.Exit(code=2)
    selected = paths or []
    if not selected and dbt is None:
        typer.echo("Provide a SQL path or --dbt.", err=True)
        raise typer.Exit(code=2)
    missing = [path for path in selected if not path.exists()]
    if missing:
        typer.echo(f"Path does not exist: {missing[0]}", err=True)
        raise typer.Exit(code=2)
    graph: LineageGraph | None = None
    if selected:
        graph = build_project(selected, dialect=dialect, schema=schema, indirect=not no_indirect)
    if dbt is not None:
        try:
            dbt_graph = build_dbt(dbt, dialect=dialect, indirect=not no_indirect)
        except DbtProjectError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        graph = dbt_graph if graph is None else _merge(graph, dbt_graph)
    if graph is None:
        raise typer.Exit(code=2)
    payload = export_json(graph)
    if output is None:
        typer.echo(payload, nl=False)
        return
    output.write_text(payload)


@app.command()
def impact(
    graph: Annotated[Path, typer.Argument(help="Graph JSON from build.")],
    change: Annotated[str | None, typer.Option("--change", help="Column whose values change.")] = (
        None
    ),
    drop: Annotated[str | None, typer.Option("--drop", help="Column that is removed.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print machine-readable JSON.")] = False,
) -> None:
    """Report change impact or drop impact for one column."""
    if (change is None) == (drop is None):
        typer.echo("Provide exactly one of --change or --drop.", err=True)
        raise typer.Exit(code=2)
    _require_graph(graph)
    loaded = load_json(graph.read_text())
    result: ImpactResult
    if change is not None:
        result = impact_of_change(loaded, change)
    else:
        result = impact_of_drop(loaded, drop or "")
    if as_json:
        typer.echo(result.model_dump_json(indent=2, by_alias=True))
        return
    typer.echo(format_impact(result))


@app.command(name="export")
def export_graph(
    graph: Annotated[Path, typer.Argument(help="Graph JSON from build.")],
    format: Annotated[
        str,
        typer.Option("--format", help="json, openlineage, or mermaid."),
    ] = "json",
    level: Annotated[str, typer.Option("--level", help="table or column.")] = "column",
) -> None:
    """Export a lineage graph."""
    if format not in {"json", "openlineage", "mermaid"}:
        typer.echo("Invalid --format. Use json, openlineage, or mermaid.", err=True)
        raise typer.Exit(code=2)
    if level not in {"table", "column"}:
        typer.echo("Invalid --level. Use table or column.", err=True)
        raise typer.Exit(code=2)
    _require_graph(graph)
    loaded = load_json(graph.read_text())
    if format == "openlineage":
        typer.echo(export_openlineage(loaded), nl=False)
    elif format == "mermaid":
        typer.echo(export_mermaid(loaded, level=level), nl=False)
    else:
        typer.echo(export_json(loaded), nl=False)


@app.command()
def serve(
    graph: Annotated[Path, typer.Argument(help="Graph JSON from build.")],
    port: Annotated[int, typer.Option("--port")] = 8765,
) -> None:
    """Serve the interactive viewer."""
    _ = (graph, port)
    _unavailable("serve")


@app.command()
def ask(
    graph: Annotated[Path, typer.Argument(help="Graph JSON from build.")],
    question: Annotated[str, typer.Argument(help="Question about lineage impact.")],
) -> None:
    """Ask the lineage agent a question."""
    _ = (graph, question)
    _unavailable("ask")
