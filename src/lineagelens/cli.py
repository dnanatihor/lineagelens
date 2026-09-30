"""Command-line skeleton. Command behaviour lands in later phases."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from lineagelens import __version__

app = typer.Typer(
    no_args_is_help=True,
    help=f"LineageLens {__version__}: column-level SQL lineage.",
)


def _unavailable(command: str) -> None:
    typer.echo(f"lineagelens {command} is not implemented yet.", err=True)
    raise typer.Exit(code=2)


@app.command()
def build(
    paths: Annotated[list[Path], typer.Argument(help="SQL files or directories.")],
    dialect: Annotated[str, typer.Option("--dialect", help="SQL dialect.")] = "postgres",
    schema: Annotated[Path | None, typer.Option("--schema", help="Path to schema.yaml.")] = None,
    dbt: Annotated[Path | None, typer.Option("--dbt", help="dbt project directory.")] = None,
    no_indirect: Annotated[bool, typer.Option("--no-indirect")] = False,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Build a lineage graph from SQL files or a dbt project."""
    _ = (paths, dialect, schema, dbt, no_indirect, output)
    _unavailable("build")


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
    _ = (graph, change, drop, as_json)
    _unavailable("impact")


@app.command()
def export(
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
    _ = (graph, format, level)
    _unavailable("export")


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
