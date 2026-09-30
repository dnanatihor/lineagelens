"""dbt manifest ingestion for the committed fixture."""

from __future__ import annotations

import json
from pathlib import Path

from lineagelens.models import Edge
from lineagelens.sources.dbt import build_dbt

PROJECT = Path(__file__).parent / "fixtures" / "dbt_project"


def test_dbt_fixture_matches_expected_edges() -> None:
    graph = build_dbt(PROJECT)
    expected = json.loads((PROJECT / "expected_edges.json").read_text())
    assert {
        (edge.source.fqn(), edge.target.fqn(), edge.type, edge.subtype) for edge in graph.edges
    } == {
        (
            Edge.model_validate(item).source.fqn(),
            Edge.model_validate(item).target.fqn(),
            item["type"],
            item["subtype"],
        )
        for item in expected["edges"]
    }
