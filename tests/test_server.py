"""API tests for the viewer server."""

from pathlib import Path

from fastapi.testclient import TestClient

from lineagelens.graph import LineageGraph
from lineagelens.models import ColumnRef, Edge, Statement
from lineagelens.project import build_project
from lineagelens.server import create_app, graph_payload, viewer_dist

WAREHOUSE = Path("tests/fixtures/warehouse")


def _column(table: str, column: str) -> ColumnRef:
    schema, name = table.split(".")
    return ColumnRef(schema_=schema, table=name, column=column)


def _chain(table_count: int) -> LineageGraph:
    edges: list[Edge] = []
    statements: list[Statement] = []
    for index in range(table_count - 1):
        source = f"s.t{index}"
        target = f"s.t{index + 1}"
        statement_id = f"file.sql#{index}"
        statements.append(
            Statement(
                id=statement_id,
                file="file.sql",
                index=index,
                line=1,
                kind="ctas",
                target_table=target,
                reads=(source,),
            )
        )
        for column in range(20):
            name = f"c{column}"
            edges.append(
                Edge(
                    source=_column(source, name),
                    target=_column(target, name),
                    type="DIRECT",
                    subtype="IDENTITY",
                    statement_id=statement_id,
                    file="file.sql",
                    line=1,
                    expression=name,
                )
            )
    return LineageGraph(statements=tuple(statements), edges=tuple(edges), diagnostics=())


def test_warehouse_graph_api() -> None:
    graph = build_project([WAREHOUSE])
    client = TestClient(create_app(graph, dist=Path("missing-dist")))
    payload = client.get("/api/graph").json()
    assert payload["view"] == "column"
    tables = {table["name"] for table in payload["tables"]}
    assert "staging.stg_orders" in tables
    assert "marts.fct_customer_revenue" in tables
    amount = next(
        edge for edge in payload["edges"] if edge["target"] == "staging.stg_orders.amount"
    )
    assert amount["file"] == "01_stg_orders.sql"
    assert amount["line"] == 1


def test_impact_and_search() -> None:
    graph = build_project([WAREHOUSE])
    client = TestClient(create_app(graph, dist=Path("missing-dist")))
    change = client.get("/api/impact", params={"change": "raw.orders.amount"}).json()
    assert set(change["direct"]) == {
        "marts.fct_customer_revenue.total_revenue",
        "staging.stg_orders.amount",
    }
    drop = client.get("/api/impact", params={"drop": "raw.orders.status"}).json()
    assert drop["failing_statements"] == ["01_stg_orders.sql#0"]
    assert drop["broken_tables"] == ["staging.stg_orders", "marts.fct_customer_revenue"]
    found = client.get("/api/search", params={"q": "raw.orders.stat"}).json()["results"]
    assert found == [{"fqn": "raw.orders.status", "table": "raw.orders", "column": "status"}]
    assert client.get("/api/impact").status_code == 400


def test_three_hundred_tables_stay_column_view() -> None:
    payload = graph_payload(_chain(300))
    assert payload["view"] == "column"
    assert len(payload["tables"]) == 300
    assert len(payload["tables"][0]["columns"]) == 20


def test_serve_opens_the_viewer() -> None:
    graph = build_project([WAREHOUSE])
    client = TestClient(create_app(graph))
    page = client.get("/")
    assert page.status_code == 200
    assert "LineageLens" in page.text
    assert (viewer_dist() / "index.html").is_file()


def test_beyond_three_hundred_tables_collapses() -> None:
    payload = graph_payload(_chain(301))
    assert payload["view"] == "table"
    assert len(payload["tables"]) == 301
