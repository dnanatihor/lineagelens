"""Per-statement lineage (SPEC.md section 5.4).

Leaf detection follows the shape pinned in
``tests/spike/test_sqlglot_lineage_shape.py``: walk ``Node.downstream`` until a
node whose ``source`` is ``exp.Table``. CTE and subquery nodes are intermediate
and never become graph columns. Indirect edges are columns used in filters,
join conditions, and GROUP BY, each linked to every output column.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import OptimizeError, SqlglotError
from sqlglot.lineage import Node, lineage
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import Scope, build_scope

from lineagelens.models import (
    ColumnRef,
    Diagnostic,
    DiagnosticCode,
    Edge,
    EdgeSubtype,
    Statement,
    StatementKind,
)
from lineagelens.schema import SchemaRegistry
from lineagelens.sources.files import statement_chunks

_UNSUPPORTED = (exp.Delete, exp.Update, exp.Drop, exp.Merge, exp.Alter, exp.Command)


@dataclass(frozen=True)
class StatementExtraction:
    """One statement, its direct edges, and any diagnostics."""

    statement: Statement
    edges: tuple[Edge, ...]
    diagnostics: tuple[Diagnostic, ...]
    output_columns: tuple[str, ...] = ()


def extract_sql(
    sql: str,
    *,
    file: str,
    dialect: str = "postgres",
    schema: SchemaRegistry | Mapping[str, Mapping[str, str]] | None = None,
    indirect: bool = True,
    index_offset: int = 0,
) -> tuple[StatementExtraction, ...]:
    """Extract column lineage. Bad SQL records a diagnostic and continues."""
    registry = schema if isinstance(schema, SchemaRegistry) else SchemaRegistry(schema)
    chunks = statement_chunks(sql, dialect)
    return tuple(
        _extract_chunk(
            chunk,
            file=file,
            index=index_offset + index,
            line=line,
            dialect=dialect,
            schema=registry,
            indirect=indirect,
        )
        for index, (chunk, line) in enumerate(chunks)
    )


def _extract_chunk(
    sql: str,
    *,
    file: str,
    index: int,
    line: int,
    dialect: str,
    schema: SchemaRegistry,
    indirect: bool,
) -> StatementExtraction:
    statement_id = f"{file}#{index}"
    try:
        parsed = sqlglot.parse(sql, dialect=dialect, error_level=sqlglot.ErrorLevel.RAISE)
    except SqlglotError as exc:
        return _failed(statement_id, file, index, line, "L001", f"Unparsable statement: {exc}")
    expressions = [expression for expression in parsed if expression is not None]
    if len(expressions) != 1:
        return _failed(statement_id, file, index, line, "L001", "Unparsable statement.")
    expression = expressions[0]
    if isinstance(expression, exp.Create):
        return _extract_create(
            expression,
            statement_id=statement_id,
            file=file,
            index=index,
            line=line,
            dialect=dialect,
            schema=schema,
            indirect=indirect,
        )
    if isinstance(expression, exp.Insert):
        return _extract_insert(
            expression,
            statement_id=statement_id,
            file=file,
            index=index,
            line=line,
            dialect=dialect,
            schema=schema,
            indirect=indirect,
        )
    if isinstance(expression, exp.Query):
        return _extract_query(
            expression,
            kind="select",
            target=None,
            statement_id=statement_id,
            file=file,
            index=index,
            line=line,
            dialect=dialect,
            schema=schema,
            source=expression,
            indirect=indirect,
        )
    if isinstance(expression, _UNSUPPORTED):
        return _failed(
            statement_id,
            file,
            index,
            line,
            "L004",
            f"Unsupported statement kind: {type(expression).__name__}.",
        )
    return _failed(statement_id, file, index, line, "L001", "Unparsable statement.")


def _extract_create(
    expression: exp.Create,
    *,
    statement_id: str,
    file: str,
    index: int,
    line: int,
    dialect: str,
    schema: SchemaRegistry,
    indirect: bool,
) -> StatementExtraction:
    query = expression.expression
    kind_name = str(expression.args.get("kind") or "").upper()
    target = _target_table(expression.this)
    if kind_name == "VIEW" and isinstance(query, exp.Query) and target is not None:
        kind: StatementKind = "create_view"
    elif kind_name == "TABLE" and isinstance(query, exp.Query) and target is not None:
        kind = "ctas"
    else:
        return _failed(
            statement_id,
            file,
            index,
            line,
            "L004",
            "Unsupported statement kind.",
            reads=_reads(expression),
            target=target,
        )
    return _extract_query(
        query,
        kind=kind,
        target=target,
        statement_id=statement_id,
        file=file,
        index=index,
        line=line,
        dialect=dialect,
        schema=schema,
        source=expression,
        indirect=indirect,
    )


def _extract_insert(
    expression: exp.Insert,
    *,
    statement_id: str,
    file: str,
    index: int,
    line: int,
    dialect: str,
    schema: SchemaRegistry,
    indirect: bool,
) -> StatementExtraction:
    query = expression.expression
    target = _target_table(expression.this)
    if not isinstance(query, exp.Query) or target is None:
        return _failed(
            statement_id,
            file,
            index,
            line,
            "L004",
            "Unsupported statement kind.",
            reads=_reads(expression),
            target=target,
        )
    names = _insert_column_names(expression.this, target, schema)
    diagnostics: list[Diagnostic] = []
    renamed = query
    if names is not None:
        renamed, matched = _rename_outputs(query, names)
        if not matched:
            diagnostics.append(
                _diagnostic(
                    "L005",
                    "INSERT column list does not match the SELECT list.",
                    statement_id,
                )
            )
    return _extract_query(
        renamed,
        kind="insert_select",
        target=target,
        statement_id=statement_id,
        file=file,
        index=index,
        line=line,
        dialect=dialect,
        schema=schema,
        source=expression,
        extra_diagnostics=tuple(diagnostics),
        indirect=indirect,
    )


def _extract_query(
    query: exp.Query,
    *,
    kind: StatementKind,
    target: str | None,
    statement_id: str,
    file: str,
    index: int,
    line: int,
    dialect: str,
    schema: SchemaRegistry,
    source: exp.Expr,
    extra_diagnostics: tuple[Diagnostic, ...] = (),
    indirect: bool = True,
) -> StatementExtraction:
    statement = Statement(
        id=statement_id,
        file=file,
        index=index,
        line=line,
        kind=kind,
        target_table=target,
        reads=_reads(source),
    )
    diagnostics = list(extra_diagnostics)
    mapping = schema.as_mapping() or None
    qualified, qualify_diagnostics = _qualify(query, mapping, dialect, statement_id)
    diagnostics.extend(qualify_diagnostics)
    edges: list[Edge] = []
    outputs: list[str] = []
    if target is not None:
        try:
            traced = lineage(None, qualified, schema=mapping, dialect=dialect)
        except SqlglotError as exc:
            diagnostics.append(
                _diagnostic("L003", f"Ambiguous or unresolved column: {exc}", statement_id)
            )
        else:
            if isinstance(traced, dict):
                outputs = _output_names(traced)
                edges.extend(
                    _edges_for_outputs(
                        traced,
                        target=target,
                        statement_id=statement_id,
                        file=file,
                        line=line,
                        dialect=dialect,
                        diagnostics=diagnostics,
                    )
                )
                if indirect:
                    edges.extend(
                        _indirect_edges(
                            qualified,
                            outputs=outputs,
                            target=target,
                            statement_id=statement_id,
                            file=file,
                            line=line,
                            dialect=dialect,
                        )
                    )
    return StatementExtraction(
        statement=statement,
        edges=_sorted_edges(edges),
        diagnostics=_unique_diagnostics(diagnostics),
        output_columns=tuple(outputs),
    )


def _qualify(
    query: exp.Query,
    mapping: dict[str, object] | None,
    dialect: str,
    statement_id: str,
) -> tuple[exp.Query, tuple[Diagnostic, ...]]:
    try:
        qualified = qualify(
            query.copy(),
            schema=mapping,
            dialect=dialect,
            identify=False,
        )
    except OptimizeError as exc:
        message = f"Ambiguous or unresolved column: {exc}"
        return query, (_diagnostic("L003", message, statement_id),)
    if not isinstance(qualified, exp.Query):
        return query, ()
    unknown = _unexpanded_star_tables(qualified)
    if unknown:
        diagnostics = tuple(
            _diagnostic(
                "L002",
                f"Unknown table {table}; star cannot be expanded.",
                statement_id,
            )
            for table in unknown
        )
        return qualified, diagnostics
    return qualified, ()


def _edges_for_outputs(
    traced: dict[str, Node],
    *,
    target: str,
    statement_id: str,
    file: str,
    line: int,
    dialect: str,
    diagnostics: list[Diagnostic],
) -> list[Edge]:
    edges: list[Edge] = []
    for output_name, node in traced.items():
        column = _output_column(node, output_name)
        if column == "*":
            _record_unknown_stars(node, statement_id, diagnostics)
            continue
        subtype = _classify(node)
        target_column = _column_on_table(target, column)
        seen: set[str] = set()
        for leaf in _leaves(node):
            source = _source_column(leaf)
            if source is None:
                if _is_star_leaf(leaf):
                    _record_unknown_stars(node, statement_id, diagnostics)
                continue
            if source.fqn() in seen:
                continue
            seen.add(source.fqn())
            edges.append(
                Edge(
                    source=source,
                    target=target_column,
                    type="DIRECT",
                    subtype=subtype,
                    expression=_snippet(node, dialect),
                    statement_id=statement_id,
                    file=file,
                    line=line,
                )
            )
    return edges


def _record_unknown_stars(node: Node, statement_id: str, diagnostics: list[Diagnostic]) -> None:
    for leaf in _leaves(node):
        source = leaf.source
        if isinstance(source, exp.Table):
            diagnostics.append(
                _diagnostic(
                    "L002",
                    f"Unknown table {_table_fqn(source)}; star cannot be expanded.",
                    statement_id,
                )
            )


def _classify(node: Node) -> EdgeSubtype:
    saw_aggregate = False
    saw_transform = False
    for current in node.walk():
        expression = current.expression
        if expression is None or isinstance(expression, exp.Table):
            continue
        if any(True for _ in expression.find_all(exp.AggFunc)):
            saw_aggregate = True
        inner = expression.this if isinstance(expression, exp.Alias) else expression
        if not isinstance(inner, exp.Column):
            saw_transform = True
    if saw_aggregate:
        return "AGGREGATION"
    if saw_transform:
        return "TRANSFORMATION"
    return "IDENTITY"


def _leaves(node: Node) -> list[Node]:
    return [current for current in node.walk() if not current.downstream]


def _source_column(leaf: Node) -> ColumnRef | None:
    source = leaf.source
    if not isinstance(source, exp.Table) or _is_star_leaf(leaf):
        return None
    column = leaf.name.rsplit(".", 1)[-1]
    return _column_on_table(_table_fqn(source), _plain_name(column))


def _is_star_leaf(leaf: Node) -> bool:
    return leaf.name.endswith(".*") or leaf.name == "*"


def _output_column(node: Node, fallback: str) -> str:
    expression = node.expression
    if isinstance(expression, exp.Alias):
        alias = expression.args.get("alias")
        if isinstance(alias, exp.Identifier) and alias.quoted:
            return f'"{alias.name}"'
    if fallback == "*":
        return "*"
    return _plain_name(fallback)


def _column_on_table(table_fqn: str, column: str) -> ColumnRef:
    database, schema, table = _split_table_fqn(table_fqn)
    return ColumnRef.model_validate(
        {"database": database, "schema": schema, "table": table, "column": column}
    )


def _split_table_fqn(table_fqn: str) -> tuple[str | None, str | None, str]:
    parts = table_fqn.split(".")
    if len(parts) == 1:
        return None, None, parts[0]
    if len(parts) == 2:
        return None, parts[0], parts[1]
    return parts[0], parts[1], parts[2]


def _insert_column_names(
    target: exp.Expr, table_fqn: str, schema: SchemaRegistry
) -> list[str] | None:
    if isinstance(target, exp.Schema) and target.expressions:
        return [_plain_name(identifier.name) for identifier in target.expressions]
    return list(schema.column_names(table_fqn) or ()) or None


def _rename_outputs(query: exp.Query, names: list[str]) -> tuple[exp.Query, bool]:
    copied = query.copy()
    select = copied if isinstance(copied, exp.Select) else copied.find(exp.Select)
    if not isinstance(select, exp.Select):
        return copied, False
    matched = len(select.expressions) == len(names)
    renamed: list[exp.Expr] = []
    for index, expression in enumerate(select.expressions):
        if index >= len(names):
            renamed.append(expression)
            continue
        inner = expression.this if isinstance(expression, exp.Alias) else expression
        renamed.append(exp.alias_(inner, names[index]))
    select.set("expressions", renamed)
    return copied, matched


def _unexpanded_star_tables(query: exp.Expr) -> tuple[str, ...]:
    if not any(True for _ in query.find_all(exp.Star)):
        return ()
    found: list[str] = []
    seen: set[str] = set()
    for table in query.find_all(exp.Table):
        fqn = _table_fqn(table)
        if fqn not in seen:
            seen.add(fqn)
            found.append(fqn)
    return tuple(found)


def _reads(expression: exp.Expr) -> tuple[str, ...]:
    cte_names = {cte.alias.lower() for cte in expression.find_all(exp.CTE) if cte.alias}
    target = _target_table(expression.this) if expression.this is not None else None
    found: list[str] = []
    seen: set[str] = set()
    for table in expression.find_all(exp.Table):
        fqn = _table_fqn(table)
        if fqn == target:
            continue
        if table.args.get("db") is None and table.name.lower() in cte_names:
            continue
        if fqn not in seen:
            seen.add(fqn)
            found.append(fqn)
    return tuple(sorted(found))


def _target_table(expression: exp.Expr | None) -> str | None:
    if isinstance(expression, exp.Schema):
        expression = expression.this
    if isinstance(expression, exp.Table):
        return _table_fqn(expression)
    return None


def _table_fqn(table: exp.Table) -> str:
    parts: list[str] = []
    for key in ("catalog", "db"):
        identifier = table.args.get(key)
        if isinstance(identifier, exp.Expr):
            parts.append(_plain_name(identifier.name))
    parts.append(_plain_name(table.name))
    return ".".join(parts)


def _plain_name(name: str) -> str:
    if len(name) >= 2 and name[0] == name[-1] and name[0] in {'"', "`"}:
        return name
    return name.lower()


def _snippet(node: Node, dialect: str) -> str:
    expression = node.expression
    if expression is None:
        return ""
    return expression.sql(dialect=dialect)[:200]


def _diagnostic(code: DiagnosticCode, message: str, statement_id: str) -> Diagnostic:
    return Diagnostic(code=code, severity="error", statement_id=statement_id, message=message)


def _failed(
    statement_id: str,
    file: str,
    index: int,
    line: int,
    code: DiagnosticCode,
    message: str,
    *,
    reads: tuple[str, ...] = (),
    target: str | None = None,
) -> StatementExtraction:
    kind: StatementKind = "unsupported"
    return StatementExtraction(
        statement=Statement(
            id=statement_id,
            file=file,
            index=index,
            line=line,
            kind=kind,
            target_table=target,
            reads=reads,
        ),
        edges=(),
        diagnostics=(_diagnostic(code, message, statement_id),),
    )


def _output_names(traced: dict[str, Node]) -> list[str]:
    names: list[str] = []
    for output_name, node in traced.items():
        column = _output_column(node, output_name)
        if column != "*":
            names.append(column)
    return names


def _indirect_edges(
    query: exp.Expr,
    *,
    outputs: list[str],
    target: str,
    statement_id: str,
    file: str,
    line: int,
    dialect: str,
) -> list[Edge]:
    if not outputs:
        return []
    scope = build_scope(query)
    if not isinstance(scope, Scope) or not isinstance(scope.expression, exp.Select):
        return []
    select = scope.expression
    columns: dict[EdgeSubtype, list[exp.Column]] = {
        "FILTER": [],
        "JOIN": [],
        "GROUP_BY": [],
    }
    for key in ("where", "having", "qualify"):
        clause = select.args.get(key)
        if isinstance(clause, exp.Expr):
            columns["FILTER"].extend(clause.find_all(exp.Column))
    joins = select.args.get("joins")
    if isinstance(joins, list):
        for join in joins:
            if isinstance(join, exp.Join):
                on = join.args.get("on")
                if isinstance(on, exp.Expr):
                    columns["JOIN"].extend(on.find_all(exp.Column))
    group = select.args.get("group")
    if isinstance(group, exp.Expr):
        columns["GROUP_BY"].extend(group.find_all(exp.Column))

    edges: list[Edge] = []
    for subtype, refs in columns.items():
        seen: set[str] = set()
        for column in refs:
            source = _resolve_scoped_column(column, scope)
            if source is None or source.fqn() in seen:
                continue
            seen.add(source.fqn())
            expression = column.sql(dialect=dialect)[:200]
            for output in outputs:
                edges.append(
                    Edge(
                        source=source,
                        target=_column_on_table(target, output),
                        type="INDIRECT",
                        subtype=subtype,
                        expression=expression,
                        statement_id=statement_id,
                        file=file,
                        line=line,
                    )
                )
    return edges


def _resolve_scoped_column(column: exp.Column, scope: Scope) -> ColumnRef | None:
    source = scope.sources.get(column.table) if column.table else None
    if isinstance(source, exp.Table):
        return _column_on_table(_table_fqn(source), _plain_name(column.name))
    return None


def _sorted_edges(edges: list[Edge]) -> tuple[Edge, ...]:
    return tuple(
        sorted(edges, key=lambda edge: (edge.source.fqn(), edge.target.fqn(), edge.subtype))
    )


def _unique_diagnostics(diagnostics: list[Diagnostic]) -> tuple[Diagnostic, ...]:
    unique: list[Diagnostic] = []
    seen: set[tuple[str, str]] = set()
    for diagnostic in diagnostics:
        key = (diagnostic.code, diagnostic.message)
        if key in seen:
            continue
        seen.add(key)
        unique.append(diagnostic)
    return tuple(unique)
