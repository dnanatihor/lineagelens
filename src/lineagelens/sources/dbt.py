"""dbt manifest ingestion.

Requires ``dbt compile`` beforehand so ``target/manifest.json`` contains ``compiled_code``.
Sources and seeds become known tables. Columns come from ``target/catalog.json`` when present.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from lineagelens.extract import extract_sql
from lineagelens.graph import LineageGraph
from lineagelens.models import Diagnostic, Edge, Statement
from lineagelens.schema import SchemaRegistry


class DbtProjectError(FileNotFoundError):
    """Raised when a dbt project has not been compiled."""


def build_dbt(
    project_dir: Path,
    *,
    dialect: str = "postgres",
    indirect: bool = True,
) -> LineageGraph:
    """Build lineage for compiled dbt models in ``project_dir``."""
    manifest_path = project_dir / "target" / "manifest.json"
    if not manifest_path.is_file():
        message = "dbt compile is required; target/manifest.json was not found"
        raise DbtProjectError(message)
    manifest = cast(dict[str, object], json.loads(manifest_path.read_text()))
    catalog_path = project_dir / "target" / "catalog.json"
    catalog: dict[str, object] = {}
    if catalog_path.is_file():
        catalog = cast(dict[str, object], json.loads(catalog_path.read_text()))
    registry = _known_tables(manifest, catalog)
    statements: list[Statement] = []
    edges: list[Edge] = []
    diagnostics: list[Diagnostic] = []
    for node in _models_in_order(manifest):
        relation = _relation_name(node)
        compiled = node.get("compiled_code")
        if not isinstance(compiled, str) or not compiled.strip() or relation is None:
            continue
        file_name = str(node.get("original_file_path") or f"{node.get('name', 'model')}.sql")
        sql = f"CREATE TABLE {relation} AS\n{compiled}"
        extracted = extract_sql(
            sql,
            file=file_name,
            dialect=dialect,
            schema=registry,
            indirect=indirect,
        )
        for result in extracted:
            statements.append(result.statement)
            edges.extend(result.edges)
            diagnostics.extend(result.diagnostics)
            if result.statement.target_table and result.output_columns:
                registry.register(
                    result.statement.target_table,
                    [(column, "UNKNOWN") for column in result.output_columns],
                )
    return LineageGraph(
        statements=tuple(statements),
        edges=tuple(edges),
        diagnostics=tuple(diagnostics),
    )


def _known_tables(manifest: dict[str, object], catalog: dict[str, object]) -> SchemaRegistry:
    tables: dict[str, dict[str, str]] = {}
    nodes = cast(dict[str, object], manifest.get("nodes") or {})
    sources = cast(dict[str, object], manifest.get("sources") or {})
    for unique_id, raw in {**nodes, **sources}.items():
        if not isinstance(raw, dict):
            continue
        node = cast(dict[str, object], raw)
        if node.get("resource_type") not in {"source", "seed"}:
            continue
        relation = _relation_name(node)
        if relation is None:
            continue
        tables[relation] = _catalog_columns(catalog, unique_id)
    return SchemaRegistry({name: columns for name, columns in tables.items() if columns})


def _catalog_columns(catalog: dict[str, object], unique_id: str) -> dict[str, str]:
    for section in ("sources", "nodes"):
        entries = catalog.get(section)
        if not isinstance(entries, dict) or unique_id not in entries:
            continue
        entry = entries[unique_id]
        if not isinstance(entry, dict):
            continue
        columns = entry.get("columns")
        if not isinstance(columns, dict):
            continue
        loaded: dict[str, str] = {}
        for name, column in columns.items():
            column_type = "UNKNOWN"
            if isinstance(column, dict) and column.get("type") is not None:
                column_type = str(column["type"])
            loaded[str(name)] = column_type
        return loaded
    return {}


def _models_in_order(manifest: dict[str, object]) -> list[dict[str, object]]:
    nodes = cast(dict[str, object], manifest.get("nodes") or {})
    models: dict[str, dict[str, object]] = {}
    for unique_id, raw in nodes.items():
        if isinstance(raw, dict) and raw.get("resource_type") == "model":
            models[unique_id] = cast(dict[str, object], raw)
    depends: dict[str, set[str]] = {}
    for unique_id, node in models.items():
        raw_depends = node.get("depends_on")
        upstream: set[str] = set()
        if isinstance(raw_depends, dict):
            refs = raw_depends.get("nodes")
            if isinstance(refs, list):
                upstream = {ref for ref in refs if isinstance(ref, str) and ref in models}
        depends[unique_id] = upstream
    remaining = set(models)
    ordered: list[str] = []
    while remaining:
        ready = sorted(unique_id for unique_id in remaining if not (depends[unique_id] & remaining))
        if not ready:
            ordered.extend(sorted(remaining))
            break
        nxt = ready[0]
        remaining.remove(nxt)
        ordered.append(nxt)
    return [models[unique_id] for unique_id in ordered]


def _relation_name(node: dict[str, object]) -> str | None:
    relation = node.get("relation_name")
    if isinstance(relation, str) and relation.strip():
        return relation.replace('"', "")
    parts = [node.get("database"), node.get("schema"), node.get("alias") or node.get("name")]
    names = [str(part) for part in parts if isinstance(part, str) and part]
    if not names:
        return None
    return ".".join(names)
