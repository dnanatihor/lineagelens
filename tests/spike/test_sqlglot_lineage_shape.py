"""Pin the sqlglot.lineage node shape used by extract.py.

Pinned against sqlglot 30.21.0 (see uv.lock). extract.py treats this shape as
the contract for step 3 of SPEC.md §5.4:

- ``lineage`` returns a ``sqlglot.lineage.Node``.
- A node carries ``name``, ``expression``, ``source``, and ``downstream``.
- ``downstream`` walks through CTE and subquery scopes. Those intermediate
  nodes are not column sources.
- A source-column leaf has an empty ``downstream`` and a ``source`` (and
  ``expression``) of type ``exp.Table``. ``node.name`` is
  ``"{alias}.{column}"``; the real table is ``source.this`` plus ``source.db``
  (schema) and ``source.args["catalog"]`` (database). The alias is not the
  table name (self-joins use ``a`` / ``b`` while ``source.name`` stays
  ``orders``).
- An output with no source column, such as ``COUNT(*)``, still has a leaf,
  but that leaf's ``source`` is not an ``exp.Table``. Those outputs get no
  direct edge.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.lineage import Node, lineage

PINNED_SQLGLOT = "30.21.0"

_CTE_SQL = """
CREATE TABLE analytics.out AS
WITH base AS (
  SELECT id, amount FROM raw.orders
),
doubled AS (
  SELECT id, amount * 2 AS amount FROM base
)
SELECT id AS order_id, amount FROM doubled
"""


def _leaves(node: Node) -> list[Node]:
    if not node.downstream:
        return [node]
    found: list[Node] = []
    for child in node.downstream:
        found.extend(_leaves(child))
    return found


def test_pinned_sqlglot_version() -> None:
    assert sqlglot.__version__ == PINNED_SQLGLOT


def test_cte_lineage_leaf_is_base_table_not_cte() -> None:
    # Walk downstream to the unique leaf. Intermediate names are CTE aliases
    # (``doubled.id``, ``base.id``). The leaf source is the physical table.
    order_id = lineage("order_id", _CTE_SQL, dialect="postgres")
    assert isinstance(order_id, Node)
    names = [node.name for node in order_id.walk()]
    assert "doubled.id" in names
    assert "base.id" in names

    leaf = _leaves(order_id)[0]
    assert leaf.downstream == []
    assert isinstance(leaf.source, exp.Table)
    assert isinstance(leaf.expression, exp.Table)
    assert leaf.source.name == "orders"
    assert leaf.source.args["db"].name == "raw"
    assert leaf.source.args.get("catalog") is None
    assert leaf.name == "orders.id"
    assert leaf.reference_node_name == ""

    amount = lineage("amount", _CTE_SQL, dialect="postgres")
    amount_leaf = _leaves(amount)[0]
    assert isinstance(amount_leaf.source, exp.Table)
    assert amount_leaf.name == "orders.amount"
    # The ``amount * 2`` projection stays on an intermediate node, not the leaf.
    assert any(isinstance(node.expression, exp.Alias) for node in amount.walk())
    assert any(
        isinstance(node.expression.this, exp.Mul)
        for node in amount.walk()
        if isinstance(node.expression, exp.Alias)
    )


def test_count_star_leaf_is_not_a_table() -> None:
    node = lineage("c", "SELECT COUNT(*) AS c", dialect="postgres")
    leaves = _leaves(node)
    assert leaves
    assert all(not isinstance(leaf.source, exp.Table) for leaf in leaves)
