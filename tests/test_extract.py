"""Direct-lineage expectations for the §9.2 statement fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lineagelens.extract import extract_sql
from lineagelens.models import Edge
from lineagelens.schema import SchemaRegistry

FIXTURES = Path(__file__).parent / "fixtures" / "statements"
SCHEMA = SchemaRegistry.from_yaml(FIXTURES / "schema.yaml")
CASES = (
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
DIALECTS = ("postgres", "snowflake")


def _key(edge: Edge) -> tuple[str, str, str, str]:
    return (edge.source.fqn(), edge.target.fqn(), edge.type, edge.subtype)


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("case", CASES)
def test_statement_direct_edges(dialect: str, case: str) -> None:
    sql = (FIXTURES / f"{case}.sql").read_text()
    expected = json.loads((FIXTURES / f"{case}.expected.json").read_text())
    results = extract_sql(sql, file=f"{case}.sql", dialect=dialect, schema=SCHEMA)
    assert len(results) == 1
    result = results[0]
    assert result.statement.id == f"{case}.sql#0"
    assert {_key(edge) for edge in result.edges} == {
        _key(Edge.model_validate(item)) for item in expected["edges"]
    }
    assert [item.code for item in result.diagnostics] == [
        item["code"] for item in expected["diagnostics"]
    ]
    assert all(edge.type == "DIRECT" for edge in result.edges)


def test_cte_reads_are_base_tables_only() -> None:
    sql = (FIXTURES / "cte_chain.sql").read_text()
    result = extract_sql(sql, file="cte_chain.sql", dialect="postgres", schema=SCHEMA)[0]
    assert result.statement.kind == "ctas"
    assert result.statement.target_table == "analytics.out"
    assert result.statement.reads == ("raw.orders",)


def test_insert_and_view_kinds() -> None:
    schema = SCHEMA
    insert = extract_sql(
        (FIXTURES / "insert_column_list.sql").read_text(),
        file="insert_column_list.sql",
        dialect="postgres",
        schema=schema,
    )[0]
    view = extract_sql(
        (FIXTURES / "create_view.sql").read_text(),
        file="create_view.sql",
        dialect="postgres",
        schema=schema,
    )[0]
    assert insert.statement.kind == "insert_select"
    assert insert.statement.target_table == "marts.summary"
    assert view.statement.kind == "create_view"
    assert view.statement.target_table == "analytics.v_orders"


def test_insert_column_count_mismatch_records_l005_and_does_not_raise() -> None:
    sql = "INSERT INTO marts.summary (customer_id, total) SELECT id FROM raw.orders"
    result = extract_sql(sql, file="mismatch.sql", dialect="postgres", schema=SCHEMA)[0]
    assert [item.code for item in result.diagnostics] == ["L005"]
    assert any(edge.target.column == "customer_id" for edge in result.edges)


def test_unresolved_column_records_l003_and_does_not_raise() -> None:
    sql = "CREATE TABLE analytics.out AS SELECT missing FROM raw.orders"
    result = extract_sql(sql, file="missing.sql", dialect="postgres", schema=SCHEMA)[0]
    assert [item.code for item in result.diagnostics] == ["L003"]


def test_unsupported_statement_records_l004_and_does_not_raise() -> None:
    result = extract_sql(
        "DELETE FROM raw.orders WHERE id = 1",
        file="delete.sql",
        dialect="postgres",
        schema=SCHEMA,
    )[0]
    assert result.statement.kind == "unsupported"
    assert result.edges == ()
    assert [item.code for item in result.diagnostics] == ["L004"]


def test_bad_statement_does_not_abort_the_next_one() -> None:
    sql = (
        "THIS IS NOT VALID SQL;\n"
        "CREATE TABLE analytics.out AS SELECT id AS order_id FROM raw.orders"
    )
    results = extract_sql(sql, file="mixed.sql", dialect="postgres", schema=SCHEMA)
    assert [item.code for item in results[0].diagnostics] == ["L001"]
    assert results[0].edges == ()
    assert {_key(edge) for edge in results[1].edges} == {
        ("raw.orders.id", "analytics.out.order_id", "DIRECT", "IDENTITY")
    }
