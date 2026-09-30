"""Project ordering, indirect edges, and diagnostics for the warehouse fixture."""

from __future__ import annotations

import json
from pathlib import Path

from lineagelens.models import Edge
from lineagelens.project import build_project

WAREHOUSE = Path(__file__).parent / "fixtures" / "warehouse"


def _key(edge: Edge) -> tuple[str, str, str, str]:
    return (edge.source.fqn(), edge.target.fqn(), edge.type, edge.subtype)


def test_warehouse_edges_match_expected_set() -> None:
    graph = build_project(
        [WAREHOUSE],
        dialect="postgres",
        schema=WAREHOUSE / "schema.yaml",
    )
    expected = json.loads((WAREHOUSE / "expected_edges.json").read_text())
    assert {_key(edge) for edge in graph.edges} == {
        _key(Edge.model_validate(item)) for item in expected["edges"]
    }


def test_indirect_edges_can_be_disabled() -> None:
    graph = build_project(
        [WAREHOUSE],
        dialect="postgres",
        schema=WAREHOUSE / "schema.yaml",
        indirect=False,
    )
    assert graph.edges
    assert {edge.type for edge in graph.edges} == {"DIRECT"}


def test_unparsable_file_does_not_abort_the_build(tmp_path: Path) -> None:
    bad = tmp_path / "bad.sql"
    bad.write_text("THIS IS NOT VALID SQL;\n")
    graph = build_project(
        [WAREHOUSE, bad],
        dialect="postgres",
        schema=WAREHOUSE / "schema.yaml",
    )
    expected = json.loads((WAREHOUSE / "expected_edges.json").read_text())
    assert {_key(edge) for edge in graph.edges} == {
        _key(Edge.model_validate(item)) for item in expected["edges"]
    }
    assert any(item.code == "L001" for item in graph.diagnostics)


def test_cyclic_tables_record_l006_and_still_build(tmp_path: Path) -> None:
    left = tmp_path / "a.sql"
    right = tmp_path / "b.sql"
    left.write_text("CREATE TABLE analytics.left_side AS SELECT id FROM analytics.right_side;\n")
    right.write_text("CREATE TABLE analytics.right_side AS SELECT id FROM analytics.left_side;\n")
    graph = build_project([tmp_path], dialect="postgres")
    assert len(graph.statements) == 2
    assert any(item.code == "L006" for item in graph.diagnostics)
