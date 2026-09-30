"""ColumnRef, Edge, and impact models follow SPEC.md §4 and §6."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lineagelens.models import (
    ChangeImpact,
    ColumnRef,
    Diagnostic,
    DropImpact,
    Edge,
    Statement,
)


def test_fqn_lowercases_unquoted_identifiers_and_preserves_quoted_ones() -> None:
    column = ColumnRef.model_validate(
        {"database": "Analytics", "schema": "Raw", "table": "Orders", "column": "Amount"}
    )
    assert column.fqn() == "analytics.raw.orders.amount"
    quoted = ColumnRef.model_validate({"schema": "raw", "table": '"Orders"', "column": "id"})
    assert quoted.fqn() == 'raw."Orders".id'


def test_edge_expression_is_capped_at_200_characters() -> None:
    payload = {
        "source": {"table": "orders", "column": "id"},
        "target": {"table": "out", "column": "id"},
        "type": "DIRECT",
        "subtype": "IDENTITY",
        "expression": "x" * 201,
        "statement_id": "file.sql#0",
        "file": "file.sql",
        "line": 1,
    }
    with pytest.raises(ValidationError):
        Edge.model_validate(payload)


def test_statement_and_diagnostic_round_trip() -> None:
    statement = Statement.model_validate(
        {
            "id": "01_stg_orders.sql#0",
            "file": "01_stg_orders.sql",
            "index": 0,
            "line": 1,
            "kind": "ctas",
            "target_table": "staging.stg_orders",
            "reads": ["raw.orders"],
        }
    )
    assert statement.reads == ("raw.orders",)
    diagnostic = Diagnostic.model_validate(
        {
            "code": "L001",
            "severity": "error",
            "statement_id": statement.id,
            "message": "Unparsable statement.",
        }
    )
    assert diagnostic.code == "L001"


def test_change_and_drop_impacts_are_distinct_models() -> None:
    change = ChangeImpact.model_validate({"direct": [], "indirect": []})
    drop = DropImpact.model_validate(
        {"failing_statements": [], "broken_tables": [], "affected_columns": []}
    )
    assert change.evidence == ()
    assert drop.evidence == ()
    assert type(change) is not type(drop)
