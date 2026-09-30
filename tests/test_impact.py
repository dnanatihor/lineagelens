"""Impact results and exports for the warehouse fixture."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
from referencing import Registry, Resource
from typer.testing import CliRunner

from lineagelens.cli import app
from lineagelens.export.json import export_json, load_json
from lineagelens.export.mermaid import export_mermaid
from lineagelens.export.openlineage import export_openlineage
from lineagelens.impact import impact_of_change, impact_of_drop
from lineagelens.models import ColumnRef
from lineagelens.project import build_project

WAREHOUSE = Path(__file__).parent / "fixtures" / "warehouse"
SCHEMA_DIR = Path(__file__).parent / "fixtures" / "openlineage"
runner = CliRunner()


def _fqns(columns: tuple[ColumnRef, ...]) -> set[str]:
    return {column.fqn() for column in columns}


def test_expected_impact_matches() -> None:
    graph = build_project([WAREHOUSE], schema=WAREHOUSE / "schema.yaml")
    expected = json.loads((WAREHOUSE / "expected_impact.json").read_text())
    amount = impact_of_change(graph, "raw.orders.amount")
    status = impact_of_change(graph, "raw.orders.status")
    dropped = impact_of_drop(graph, "raw.orders.status")
    email = impact_of_drop(graph, "raw.customers.email")
    amount_direct = expected["change"]["raw.orders.amount"]["direct"]
    status_change = expected["change"]["raw.orders.status"]
    status_drop = expected["drop"]["raw.orders.status"]
    assert _fqns(amount.direct) == {ColumnRef.model_validate(item).fqn() for item in amount_direct}
    assert _fqns(amount.indirect) == set()
    assert amount.direct
    assert {edge.file for edge in amount.evidence}
    assert all(edge.line >= 1 for edge in amount.evidence)
    assert _fqns(status.direct) == set()
    assert _fqns(status.indirect) == {
        ColumnRef.model_validate(item).fqn() for item in status_change["indirect"]
    }
    assert dropped.failing_statements == tuple(status_drop["failing_statements"])
    assert set(dropped.broken_tables) == set(status_drop["broken_tables"])
    assert _fqns(dropped.affected_columns) == {
        ColumnRef.model_validate(item).fqn() for item in status_drop["affected_columns"]
    }
    assert email.failing_statements == ()
    assert email.broken_tables == ()
    assert email.affected_columns == ()


def test_openlineage_export_validates_against_vendored_schema() -> None:
    graph = build_project([WAREHOUSE], schema=WAREHOUSE / "schema.yaml")
    document = json.loads(export_openlineage(graph))
    facet_schema = json.loads((SCHEMA_DIR / "ColumnLineageDatasetFacet.json").read_text())
    core_schema = json.loads((SCHEMA_DIR / "OpenLineage.json").read_text())
    registry = Registry().with_resources(
        [
            (core_schema["$id"], Resource.from_contents(core_schema)),
            (facet_schema["$id"], Resource.from_contents(facet_schema)),
        ]
    )
    validator = jsonschema.Draft202012Validator(facet_schema, registry=registry)
    assert document["datasets"]
    for dataset in document["datasets"]:
        validator.validate({"columnLineage": dataset["facets"]["columnLineage"]})


def test_mermaid_table_snapshot() -> None:
    graph = build_project([WAREHOUSE], schema=WAREHOUSE / "schema.yaml")
    assert export_mermaid(graph, level="table") == (
        "flowchart LR\n"
        "  raw_customers --> marts_fct_customer_revenue\n"
        "  raw_orders --> staging_stg_orders\n"
        "  staging_stg_orders --> marts_fct_customer_revenue\n"
    )


def test_json_export_round_trip() -> None:
    graph = build_project([WAREHOUSE], schema=WAREHOUSE / "schema.yaml")
    loaded = load_json(export_json(graph))
    assert len(loaded.edges) == len(graph.edges)
    assert loaded.statements[0].id == "01_stg_orders.sql#0"


def test_impact_cli_prints_file_and_line(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    built = runner.invoke(
        app,
        [
            "build",
            str(WAREHOUSE),
            "--schema",
            str(WAREHOUSE / "schema.yaml"),
            "-o",
            str(graph_path),
        ],
    )
    assert built.exit_code == 0
    reported = runner.invoke(app, ["impact", str(graph_path), "--drop", "raw.orders.status"])
    assert reported.exit_code == 0
    assert "01_stg_orders.sql:1" in reported.stdout
    assert "staging.stg_orders" in reported.stdout
