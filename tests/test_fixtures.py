"""Phase 0 checks that fixture JSON loads into the core models and matches §9.1."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from lineagelens.models import ChangeImpact, Diagnostic, DropImpact, Edge

FIXTURES = Path(__file__).parent / "fixtures"
WAREHOUSE = FIXTURES / "warehouse"
STATEMENTS = FIXTURES / "statements"

STATEMENT_CASES = (
    "cte_chain",
    "nested_subquery",
    "union_all",
    "insert_column_list",
    "insert_no_column_list",
    "create_view",
    "select_star_known",
    "select_star_unknown",
    "case_expression",
    "window_function",
    "self_join",
    "unparsable",
)


def _column_fqn(payload: dict[str, object]) -> str:
    from lineagelens.models import ColumnRef

    return ColumnRef.model_validate(payload).fqn()


def _edge_key(edge: Edge) -> tuple[str, str, str, str]:
    return (edge.source.fqn(), edge.target.fqn(), edge.type, edge.subtype)


def test_warehouse_edges_match_spec_and_validate() -> None:
    payload = json.loads((WAREHOUSE / "expected_edges.json").read_text())
    edges = [Edge.model_validate(item) for item in payload["edges"]]
    assert len(edges) == len({_edge_key(edge) for edge in edges})

    stg = "staging.stg_orders"
    fct = "marts.fct_customer_revenue"
    stg_columns = ("order_id", "customer_id", "amount", "ordered_at")
    fct_columns = ("customer_id", "country", "total_revenue", "order_count")

    expected = {
        ("raw.orders.id", f"{stg}.order_id", "DIRECT", "IDENTITY"),
        ("raw.orders.customer_id", f"{stg}.customer_id", "DIRECT", "IDENTITY"),
        ("raw.orders.amount", f"{stg}.amount", "DIRECT", "TRANSFORMATION"),
        ("raw.orders.created_at", f"{stg}.ordered_at", "DIRECT", "IDENTITY"),
        ("raw.customers.id", f"{fct}.customer_id", "DIRECT", "IDENTITY"),
        ("raw.customers.country", f"{fct}.country", "DIRECT", "TRANSFORMATION"),
        (f"{stg}.amount", f"{fct}.total_revenue", "DIRECT", "AGGREGATION"),
    }
    expected.update(
        ("raw.orders.status", f"{stg}.{column}", "INDIRECT", "FILTER") for column in stg_columns
    )
    for source in (f"{stg}.customer_id", "raw.customers.id"):
        expected.update((source, f"{fct}.{column}", "INDIRECT", "JOIN") for column in fct_columns)
    for source in ("raw.customers.id", "raw.customers.country"):
        expected.update(
            (source, f"{fct}.{column}", "INDIRECT", "GROUP_BY") for column in fct_columns
        )

    assert {_edge_key(edge) for edge in edges} == expected
    assert not any(edge.type == "DIRECT" and edge.target.column == "order_count" for edge in edges)


def test_warehouse_impact_matches_spec_and_validates() -> None:
    payload = json.loads((WAREHOUSE / "expected_impact.json").read_text())
    stg = "staging.stg_orders"
    fct = "marts.fct_customer_revenue"
    stg_columns = {
        f"{stg}.order_id",
        f"{stg}.customer_id",
        f"{stg}.amount",
        f"{stg}.ordered_at",
    }
    fct_columns = {
        f"{fct}.customer_id",
        f"{fct}.country",
        f"{fct}.total_revenue",
        f"{fct}.order_count",
    }

    amount = ChangeImpact.model_validate(payload["change"]["raw.orders.amount"])
    status = ChangeImpact.model_validate(payload["change"]["raw.orders.status"])
    dropped_status = DropImpact.model_validate(payload["drop"]["raw.orders.status"])
    dropped_email = DropImpact.model_validate(payload["drop"]["raw.customers.email"])

    assert {_column_fqn(column.model_dump(by_alias=True)) for column in amount.direct} == {
        f"{stg}.amount",
        f"{fct}.total_revenue",
    }
    assert amount.indirect == ()
    assert status.direct == ()
    assert {_column_fqn(column.model_dump(by_alias=True)) for column in status.indirect} == (
        stg_columns | fct_columns
    )
    assert dropped_status.failing_statements == ("01_stg_orders.sql#0",)
    assert set(dropped_status.broken_tables) == {stg, fct}
    assert {
        _column_fqn(column.model_dump(by_alias=True)) for column in dropped_status.affected_columns
    } == (stg_columns | fct_columns)
    assert dropped_email.failing_statements == ()
    assert dropped_email.broken_tables == ()
    assert dropped_email.affected_columns == ()


def test_warehouse_schema_declares_raw_tables() -> None:
    schema = yaml.safe_load((WAREHOUSE / "schema.yaml").read_text())
    assert set(schema["raw.orders"]) == {
        "id",
        "customer_id",
        "amount",
        "created_at",
        "status",
    }
    assert set(schema["raw.customers"]) == {"id", "country", "email"}


def test_statement_cases_load_against_models() -> None:
    for case in STATEMENT_CASES:
        sql_path = STATEMENTS / f"{case}.sql"
        expected_path = STATEMENTS / f"{case}.expected.json"
        assert sql_path.is_file()
        payload = json.loads(expected_path.read_text())
        edges = [Edge.model_validate(item) for item in payload["edges"]]
        diagnostics = [Diagnostic.model_validate(item) for item in payload["diagnostics"]]
        assert all(edge.type == "DIRECT" for edge in edges)
        if case == "unparsable":
            assert edges == []
            assert [item.code for item in diagnostics] == ["L001"]
        elif case == "select_star_unknown":
            assert edges == []
            assert [item.code for item in diagnostics] == ["L002"]
        else:
            assert edges
            assert diagnostics == []


def test_dbt_fixture_and_expected_edges_load() -> None:
    project = FIXTURES / "dbt_project"
    manifest = json.loads((project / "target" / "manifest.json").read_text())
    catalog = json.loads((project / "target" / "catalog.json").read_text())
    models = [node for node in manifest["nodes"].values() if node["resource_type"] == "model"]
    assert len(models) == 1
    assert models[0]["compiled_code"]
    assert models[0]["relation_name"] == "analytics.staging.stg_orders"
    assert "id" in catalog["sources"]["source.lineagelens_fixture.raw.orders"]["columns"]
    edges = [
        Edge.model_validate(item)
        for item in json.loads((project / "expected_edges.json").read_text())["edges"]
    ]
    assert {_edge_key(edge) for edge in edges} == {
        (
            "analytics.raw.orders.id",
            "analytics.staging.stg_orders.order_id",
            "DIRECT",
            "IDENTITY",
        ),
        (
            "analytics.raw.orders.amount",
            "analytics.staging.stg_orders.amount",
            "DIRECT",
            "TRANSFORMATION",
        ),
    }
